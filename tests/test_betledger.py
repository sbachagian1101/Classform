from datetime import datetime, timedelta

from betledger_store import Ledger, Bet, Settings, OPEN, WON, LOST, VOID
from betledger_reader import parse_slip_text, synth_ref

SLIP = """My Bets
Balance £250.00
Man City to win
Man City v Arsenal
@ 1.80
Stake £20.00
Won
Returns £36.00
Bet ref AB12345678
Liverpool v Chelsea - Over 2.5 Goals
@ 7/2
Stake £10.00
Lost
Bet ref CD98765432
Horse Racing - Enable
Ascot 14:30 12/10/2026 14:02
@ 3.5
Stake £5.00
To Return £17.50
Bet ref EF11112222
"""


def test_parse_slip_text():
    res = parse_slip_text(SLIP)
    assert res.balance == 250.0
    assert [b.bet_ref for b in res.bets] == ["AB12345678", "CD98765432", "EF11112222"]
    won, lost, opn = res.bets
    assert won.status == WON and won.stake == 20 and won.odds == 1.8 and won.returns == 36 and won.profit == 16
    assert lost.status == LOST and lost.odds == 4.5 and lost.returns == 0 and lost.profit == -10
    assert opn.status == OPEN and opn.returns == 0 and opn.profit == 0 and opn.placed_at.startswith("2026-10-12T14:02")
    assert not won.needs_review


def test_synth_ref_when_missing():
    res = parse_slip_text("Some Horse\n@ 2.0\nStake 5.00\n")
    assert res.bets[0].bet_ref == synth_ref("Some Horse", 5.0, None)
    assert res.bets[0].needs_review


def test_ledger_dedupe_and_settle(tmp_path):
    led = Ledger(tmp_path / "t.sqlite3")
    b = Bet("X1", "Sel", stake=10, odds=2.0, status=OPEN)
    assert led.upsert_bets([b]) == (1, 0)
    # same slip re-read as won
    won = Bet("X1", "Sel", stake=10, odds=2.0, status=WON, returns=20, settled_at=datetime.now().isoformat())
    assert led.upsert_bets([won]) == (0, 1)
    # stale open screenshot must not regress the settled bet
    assert led.upsert_bets([b]) == (0, 0)
    assert led.all_bets()[0].status == WON
    assert led.day_summary().profit == 10


def test_daily_limits_and_opening_balance(tmp_path):
    led = Ledger(tmp_path / "t.sqlite3")
    led.save_settings(Settings(daily_win_limit=50, daily_loss_limit=30, day_start="00:00", opening_balance=100))
    now = datetime.now().replace(hour=12)
    led.add_balance(200, now - timedelta(days=1))   # yesterday's snapshot becomes today's opening
    led.upsert_bets([
        Bet("A", "a", stake=10, status=LOST, returns=0, settled_at=now.isoformat()),
        Bet("B", "b", stake=25, status=LOST, returns=0, settled_at=now.isoformat()),
        Bet("C", "c", stake=5, status=VOID, returns=5, settled_at=now.isoformat()),
        Bet("D", "d", stake=40, status=OPEN),
        Bet("E", "e", stake=10, status=LOST, returns=0, settled_at=(now - timedelta(days=2)).isoformat()),
    ])
    s = led.day_summary(now)
    assert s.opening_balance == 200
    assert s.profit == -35 and s.settled == 3 and s.open_stake == 40
    assert s.loss_limit_hit and not s.win_limit_hit
    assert any("LOSS limit" in a for a in s.alerts)
    assert led.current_balance() == 200 - 35


def test_win_limit_and_projection(tmp_path):
    led = Ledger(tmp_path / "t.sqlite3")
    led.save_settings(Settings(daily_win_limit=20, daily_loss_limit=30))
    now = datetime.now().replace(hour=12)
    led.upsert_bets([Bet("A", "a", stake=10, odds=3, status=WON, returns=30, settled_at=now.isoformat())])
    s = led.day_summary(now)
    assert s.win_limit_hit and any("WIN limit" in a for a in s.alerts)
    led.upsert_bets([Bet("B", "b", stake=60, status=OPEN)])
    s = led.day_summary(now)
    assert any(a.startswith("Warning") for a in s.alerts)


def test_day_start_rollover(tmp_path):
    led = Ledger(tmp_path / "t.sqlite3")
    led.save_settings(Settings(day_start="06:00"))
    at_3am = datetime.now().replace(hour=3, minute=0)
    start, end = led.day_window(at_3am)
    assert start.hour == 6 and start.date() == (at_3am - timedelta(days=1)).date()
