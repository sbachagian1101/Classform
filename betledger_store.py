"""SQLite-backed betting ledger with daily win/loss limits.

Bets are keyed by the bookmaker's bet reference so repeated screenshots of the
same slip never create duplicates; re-reading a settled slip just updates the
status and return of the existing row.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_DB = Path(__file__).with_name("betledger.sqlite3")
OPEN, WON, LOST, VOID, CASHED_OUT = "open", "won", "lost", "void", "cashed_out"
STATUSES = (OPEN, WON, LOST, VOID, CASHED_OUT)


@dataclass
class Bet:
    bet_ref: str
    selection: str
    event: str = ""
    stake: float = 0.0
    odds: Optional[float] = None
    status: str = OPEN
    returns: float = 0.0          # amount paid back (0 when lost / open)
    placed_at: Optional[str] = None   # ISO datetime
    settled_at: Optional[str] = None  # ISO datetime
    bet_type: str = "single"
    confidence: float = 1.0       # reader confidence, 0..1
    needs_review: bool = False
    source: str = "manual"

    @property
    def profit(self) -> float:
        if self.status == OPEN:
            return 0.0
        return round(self.returns - self.stake, 2)

    def to_row(self) -> dict:
        d = asdict(self)
        d["profit"] = self.profit
        return d


@dataclass
class Settings:
    daily_win_limit: float = 0.0    # 0 = off
    daily_loss_limit: float = 0.0   # 0 = off, stored as positive number
    day_start: str = "00:00"        # local time the betting day rolls over
    opening_balance: float = 0.0


@dataclass
class DaySummary:
    day: date
    opening_balance: Optional[float]
    staked: float
    returned: float
    profit: float
    open_stake: float
    settled: int
    open_bets: int
    alerts: list[str] = field(default_factory=list)
    win_limit_hit: bool = False
    loss_limit_hit: bool = False


class Ledger:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    # ---------- schema ----------
    def _init(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS bets (
                bet_ref TEXT PRIMARY KEY,
                selection TEXT NOT NULL,
                event TEXT DEFAULT '',
                stake REAL NOT NULL,
                odds REAL,
                status TEXT NOT NULL,
                returns REAL DEFAULT 0,
                placed_at TEXT,
                settled_at TEXT,
                bet_type TEXT DEFAULT 'single',
                confidence REAL DEFAULT 1,
                needs_review INTEGER DEFAULT 0,
                source TEXT DEFAULT 'manual',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                ts TEXT PRIMARY KEY,
                balance REAL NOT NULL,
                source TEXT DEFAULT 'manual'
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        c.commit()

    # ---------- settings ----------
    def get_settings(self) -> Settings:
        rows = {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")}
        s = Settings()
        s.daily_win_limit = float(rows.get("daily_win_limit", s.daily_win_limit))
        s.daily_loss_limit = float(rows.get("daily_loss_limit", s.daily_loss_limit))
        s.day_start = rows.get("day_start", s.day_start)
        s.opening_balance = float(rows.get("opening_balance", s.opening_balance))
        return s

    def save_settings(self, s: Settings) -> None:
        for k, v in asdict(s).items():
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )
        self.conn.commit()

    # ---------- bets ----------
    def upsert_bets(self, bets: Iterable[Bet]) -> tuple[int, int]:
        """Insert new bets or update existing ones. Returns (inserted, updated).

        A settled status never regresses to open when an older screenshot is
        re-read after a newer one.
        """
        inserted = updated = 0
        now = datetime.now().isoformat(timespec="seconds")
        for b in bets:
            if b.status not in STATUSES:
                raise ValueError(f"unknown status {b.status!r}")
            existing = self.conn.execute("SELECT * FROM bets WHERE bet_ref=?", (b.bet_ref,)).fetchone()
            if existing is None:
                self.conn.execute(
                    """INSERT INTO bets(bet_ref, selection, event, stake, odds, status, returns, placed_at,
                       settled_at, bet_type, confidence, needs_review, source, updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (b.bet_ref, b.selection, b.event, b.stake, b.odds, b.status, b.returns, b.placed_at,
                     b.settled_at, b.bet_type, b.confidence, int(b.needs_review), b.source, now),
                )
                inserted += 1
            else:
                if existing["status"] != OPEN and b.status == OPEN:
                    continue  # stale screenshot, keep the settled row
                self.conn.execute(
                    """UPDATE bets SET selection=COALESCE(NULLIF(?,''), selection), event=COALESCE(NULLIF(?,''), event),
                       stake=?, odds=COALESCE(?, odds), status=?, returns=?, placed_at=COALESCE(placed_at, ?),
                       settled_at=COALESCE(?, settled_at), bet_type=?, confidence=?, needs_review=?, source=?, updated_at=?
                       WHERE bet_ref=?""",
                    (b.selection, b.event, b.stake, b.odds, b.status, b.returns, b.placed_at, b.settled_at,
                     b.bet_type, b.confidence, int(b.needs_review), b.source, now, b.bet_ref),
                )
                updated += 1
        self.conn.commit()
        return inserted, updated

    def settle(self, bet_ref: str, status: str, returns: float, settled_at: Optional[datetime] = None) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        ts = (settled_at or datetime.now()).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE bets SET status=?, returns=?, settled_at=?, needs_review=0, updated_at=? WHERE bet_ref=?",
            (status, returns, ts, ts, bet_ref),
        )
        self.conn.commit()

    def mark_reviewed(self, bet_ref: str) -> None:
        self.conn.execute("UPDATE bets SET needs_review=0 WHERE bet_ref=?", (bet_ref,))
        self.conn.commit()

    def delete(self, bet_ref: str) -> None:
        self.conn.execute("DELETE FROM bets WHERE bet_ref=?", (bet_ref,))
        self.conn.commit()

    def all_bets(self) -> list[Bet]:
        rows = self.conn.execute("SELECT * FROM bets ORDER BY COALESCE(placed_at, updated_at) DESC").fetchall()
        return [self._row_to_bet(r) for r in rows]

    @staticmethod
    def _row_to_bet(r: sqlite3.Row) -> Bet:
        return Bet(
            bet_ref=r["bet_ref"], selection=r["selection"], event=r["event"], stake=r["stake"], odds=r["odds"],
            status=r["status"], returns=r["returns"], placed_at=r["placed_at"], settled_at=r["settled_at"],
            bet_type=r["bet_type"], confidence=r["confidence"], needs_review=bool(r["needs_review"]), source=r["source"],
        )

    # ---------- balance ----------
    def add_balance(self, balance: float, ts: Optional[datetime] = None, source: str = "manual") -> None:
        t = (ts or datetime.now()).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO balance_snapshots(ts, balance, source) VALUES(?,?,?) ON CONFLICT(ts) DO UPDATE SET balance=excluded.balance",
            (t, balance, source),
        )
        self.conn.commit()

    def balances(self) -> list[tuple[str, float]]:
        return [(r["ts"], r["balance"]) for r in self.conn.execute("SELECT ts, balance FROM balance_snapshots ORDER BY ts")]

    # ---------- daily maths ----------
    def day_window(self, when: Optional[datetime] = None) -> tuple[datetime, datetime]:
        s = self.get_settings()
        hh, mm = (int(x) for x in s.day_start.split(":"))
        now = when or datetime.now()
        start = datetime.combine(now.date(), time(hh, mm))
        if now < start:
            start -= timedelta(days=1)
        return start, start + timedelta(days=1)

    def day_summary(self, when: Optional[datetime] = None) -> DaySummary:
        s = self.get_settings()
        start, end = self.day_window(when)
        lo, hi = start.isoformat(), end.isoformat()
        bets = self.all_bets()

        settled_today = [b for b in bets if b.status != OPEN and b.settled_at and lo <= b.settled_at < hi]
        open_bets = [b for b in bets if b.status == OPEN]
        staked = round(sum(b.stake for b in settled_today), 2)
        returned = round(sum(b.returns for b in settled_today), 2)
        profit = round(returned - staked, 2)

        opening: Optional[float] = None
        for ts, bal in self.balances():
            if lo <= ts < hi:
                opening = bal
                break
        if opening is None:
            # Latest snapshot before today, else the configured opening balance.
            before = [bal for ts, bal in self.balances() if ts < lo]
            opening = before[-1] if before else (s.opening_balance or None)

        summary = DaySummary(
            day=start.date(), opening_balance=opening, staked=staked, returned=returned, profit=profit,
            open_stake=round(sum(b.stake for b in open_bets), 2), settled=len(settled_today), open_bets=len(open_bets),
        )
        if s.daily_win_limit > 0 and profit >= s.daily_win_limit:
            summary.win_limit_hit = True
            summary.alerts.append(
                f"Daily WIN limit reached: +{profit:.2f} is at or above your {s.daily_win_limit:.2f} target. Consider stopping for the day.")
        if s.daily_loss_limit > 0 and profit <= -s.daily_loss_limit:
            summary.loss_limit_hit = True
            summary.alerts.append(
                f"Daily LOSS limit reached: {profit:.2f} is at or below your -{s.daily_loss_limit:.2f} limit. Stop betting for today.")
        elif s.daily_loss_limit > 0 and profit - summary.open_stake <= -s.daily_loss_limit:
            summary.alerts.append(
                f"Warning: if every open bet loses you would be at {profit - summary.open_stake:.2f}, past your loss limit.")
        return summary

    def current_balance(self) -> Optional[float]:
        """Best estimate of the live balance: latest snapshot plus everything settled since it."""
        snaps = self.balances()
        if not snaps:
            return None
        ts, bal = snaps[-1]
        for b in self.all_bets():
            if b.status != OPEN and b.settled_at and b.settled_at > ts:
                bal += b.profit
        return round(bal, 2)
