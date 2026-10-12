from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from betledger_store import Ledger, Settings, Bet, OPEN, WON, LOST, VOID, CASHED_OUT, STATUSES
from betledger_reader import read_screenshot, parse_slip_text, _vision_available

st.set_page_config(page_title="BetLedger", page_icon="📒", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root { --bl-green:#173f35; --bl-gold:#b78b3c; --bl-ink:#1d2724; --bl-red:#9a3d38; }
.block-container { max-width: 1180px; padding-top: 1rem; }
.bl-hero { background:linear-gradient(135deg,#173f35,#25584a); color:white; padding:22px 24px; border-radius:22px; margin-bottom:14px; }
.bl-hero h1 { color:white; margin:0; font-size:2rem; }
.bl-hero p { margin:.35rem 0 0; opacity:.9; }
[data-testid="stMetric"] { background:#fff; border:1px solid #ece7dc; padding:10px; border-radius:16px; }
.stButton>button { border-radius:999px; min-height:44px; font-weight:700; }
</style>
<div class="bl-hero">
  <h1>📒 BetLedger</h1>
  <p>Drop a Bet365 screenshot → bets are read and logged → profit/loss and your daily limits update instantly.</p>
</div>
""", unsafe_allow_html=True)


@st.cache_resource
def _ledger() -> Ledger:
    return Ledger()


ledger = _ledger()
settings = ledger.get_settings()


def _show_alerts() -> None:
    s = ledger.day_summary()
    for a in s.alerts:
        (st.error if ("LOSS limit" in a) else st.warning if a.startswith("Warning") else st.success)(a)
    return s


# ---------------- Sidebar: limits & balance ----------------
with st.sidebar:
    st.header("Limits")
    win = st.number_input("Daily win limit (0 = off)", min_value=0.0, value=float(settings.daily_win_limit), step=10.0)
    loss = st.number_input("Daily loss limit (0 = off)", min_value=0.0, value=float(settings.daily_loss_limit), step=10.0)
    day_start = st.text_input("Betting day starts at (HH:MM)", value=settings.day_start)
    opening = st.number_input("Default opening balance", value=float(settings.opening_balance), step=10.0)
    if st.button("Save limits", use_container_width=True):
        try:
            datetime.strptime(day_start, "%H:%M")
        except ValueError:
            st.error("Day start must be HH:MM")
        else:
            ledger.save_settings(Settings(win, loss, day_start, opening))
            st.success("Saved")
            st.rerun()
    st.divider()
    st.header("Balance snapshot")
    bal_in = st.number_input("Account balance now", value=0.0, step=10.0)
    if st.button("Record balance", use_container_width=True):
        ledger.add_balance(bal_in)
        st.success("Recorded")
        st.rerun()

# ---------------- Today ----------------
summary = _show_alerts()
cur_bal = ledger.current_balance()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Opening balance", "—" if summary.opening_balance is None else f"{summary.opening_balance:,.2f}")
c2.metric("Today's P/L", f"{summary.profit:+,.2f}", delta=f"{summary.settled} settled")
c3.metric("Staked today", f"{summary.staked:,.2f}")
c4.metric("Open stake", f"{summary.open_stake:,.2f}", delta=f"{summary.open_bets} open")
c5.metric("Est. balance", "—" if cur_bal is None else f"{cur_bal:,.2f}")

tab_add, tab_bets, tab_history = st.tabs(["Add from screenshot", "Bets & review", "History"])

# ---------------- Add ----------------
with tab_add:
    reader_ok = _vision_available()
    st.caption("Reader: " + ("Claude vision (with OCR fallback)" if reader_ok else "local Tesseract OCR only. Set ANTHROPIC_API_KEY for the more accurate Claude reader."))
    files = st.file_uploader("Bet slip / My Bets screenshots", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
    pasted = st.text_area("…or paste the slip text", height=120, placeholder="Man City to win\nMan City v Arsenal\n@ 1.80\nStake 20.00\nWon\nReturns 36.00\nBet ref AB12345678")
    if st.button("Read & log", type="primary", use_container_width=True):
        results = []
        for f in files or []:
            mt = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[f.name.rsplit(".", 1)[-1].lower()]
            try:
                results.append((f.name, read_screenshot(f.getvalue(), mt)))
            except Exception as e:  # noqa: BLE001
                st.error(f"{f.name}: {e}")
        if pasted.strip():
            results.append(("pasted text", parse_slip_text(pasted, source="paste")))
        total_in = total_up = 0
        for name, res in results:
            for w in res.warnings or []:
                st.warning(f"{name}: {w}")
            if res.balance is not None:
                ledger.add_balance(res.balance, source=res.reader)
                st.info(f"{name}: balance {res.balance:,.2f} recorded")
            ins, upd = ledger.upsert_bets(res.bets)
            total_in += ins
            total_up += upd
            if res.bets:
                st.dataframe(pd.DataFrame([b.to_row() for b in res.bets])[["bet_ref", "selection", "event", "stake", "odds", "status", "returns", "profit", "confidence"]], hide_index=True, use_container_width=True)
        if results:
            st.success(f"Logged {total_in} new bet(s), updated {total_up}.")
            st.rerun()
        else:
            st.warning("Upload a screenshot or paste slip text first.")

# ---------------- Bets & review ----------------
with tab_bets:
    bets = ledger.all_bets()
    if not bets:
        st.info("No bets yet.")
    else:
        review = [b for b in bets if b.needs_review]
        if review:
            st.subheader(f"Needs review ({len(review)})")
            st.caption("Low-confidence reads or bets without a Bet365 reference. Confirm or fix them.")
        for b in review:
            with st.expander(f"{b.selection} — stake {b.stake:.2f} — {b.status}", expanded=False):
                cols = st.columns([2, 1, 1, 1, 1])
                sel = cols[0].text_input("Selection", b.selection, key=f"sel{b.bet_ref}")
                stake = cols[1].number_input("Stake", value=float(b.stake), key=f"stk{b.bet_ref}")
                odds = cols[2].number_input("Odds", value=float(b.odds or 0), key=f"odd{b.bet_ref}")
                status = cols[3].selectbox("Status", STATUSES, index=STATUSES.index(b.status), key=f"sta{b.bet_ref}")
                ret = cols[4].number_input("Returns", value=float(b.returns), key=f"ret{b.bet_ref}")
                k1, k2 = st.columns(2)
                if k1.button("Confirm", key=f"ok{b.bet_ref}", use_container_width=True):
                    ledger.upsert_bets([Bet(b.bet_ref, sel, b.event, stake, odds or None, status, ret, b.placed_at, b.settled_at, b.bet_type, 1.0, False, b.source)])
                    ledger.mark_reviewed(b.bet_ref)
                    st.rerun()
                if k2.button("Delete", key=f"del{b.bet_ref}", use_container_width=True):
                    ledger.delete(b.bet_ref)
                    st.rerun()

        open_bets = [b for b in bets if b.status == OPEN]
        if open_bets:
            st.subheader(f"Open bets ({len(open_bets)})")
            st.caption("Settle here if you don't want to re-screenshot the settled slip.")
        for b in open_bets:
            cols = st.columns([3, 1, 1, 1, 1])
            cols[0].write(f"**{b.selection}** · {b.event} · stake {b.stake:.2f} @ {b.odds or '?'}")
            if cols[1].button("Won", key=f"w{b.bet_ref}"):
                ledger.settle(b.bet_ref, WON, round(b.stake * (b.odds or 1), 2)); st.rerun()
            if cols[2].button("Lost", key=f"l{b.bet_ref}"):
                ledger.settle(b.bet_ref, LOST, 0.0); st.rerun()
            if cols[3].button("Void", key=f"v{b.bet_ref}"):
                ledger.settle(b.bet_ref, VOID, b.stake); st.rerun()
            co = cols[4].number_input("Cash out", value=0.0, key=f"c{b.bet_ref}", label_visibility="collapsed")
            if co > 0 and cols[4].button("Apply", key=f"ca{b.bet_ref}"):
                ledger.settle(b.bet_ref, CASHED_OUT, co); st.rerun()

        st.subheader("All bets")
        df = pd.DataFrame([b.to_row() for b in bets])
        st.dataframe(df[["placed_at", "settled_at", "selection", "event", "bet_type", "stake", "odds", "status", "returns", "profit", "bet_ref", "source"]], hide_index=True, use_container_width=True)
        st.download_button("Export CSV", df.to_csv(index=False).encode(), "betledger.csv", "text/csv")

# ---------------- History ----------------
with tab_history:
    bets = [b for b in ledger.all_bets() if b.status != OPEN and b.settled_at]
    if not bets:
        st.info("Nothing settled yet.")
    else:
        df = pd.DataFrame([b.to_row() for b in bets])
        df["day"] = pd.to_datetime(df["settled_at"]).dt.date
        daily = df.groupby("day").agg(bets=("bet_ref", "count"), staked=("stake", "sum"), returned=("returns", "sum"), profit=("profit", "sum")).reset_index().sort_values("day")
        daily["cumulative"] = daily["profit"].cumsum()
        st.line_chart(daily.set_index("day")["cumulative"], height=240)
        st.dataframe(daily, hide_index=True, use_container_width=True)
        if settings.daily_win_limit or settings.daily_loss_limit:
            hits = daily[(daily["profit"] >= settings.daily_win_limit if settings.daily_win_limit else False) | (daily["profit"] <= -settings.daily_loss_limit if settings.daily_loss_limit else False)]
            st.caption(f"Days a limit was hit: {len(hits)} of {len(daily)}")
