# BetLedger — screenshot-driven betting ledger

Logs Bet365 bets from screenshots (no account access, no scraping), works out
profit/loss per bet, and alerts when a daily win or loss limit is hit.

## Files

- `betledger_app.py` — Streamlit UI
- `betledger_store.py` — SQLite ledger, daily maths, limit alerts
- `betledger_reader.py` — screenshot → bets (Claude vision, Tesseract fallback, text parser)
- `tests/test_betledger.py`

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # for the Claude vision reader (recommended)
# or, for local-only OCR: install tesseract and `pip install pytesseract pillow`
streamlit run betledger_app.py
```

## Daily workflow

1. Set your daily win / loss limit in the sidebar once.
2. Record your balance when you start (or let a screenshot that shows the balance do it).
3. After placing a bet, screenshot the slip and drop it on **Add from screenshot**.
4. When bets settle, screenshot the **Settled** list and drop it again. Same bet reference → row updates, no duplicate.
   Or press Won / Lost / Void on the open bet.
5. Alerts appear at the top as soon as today's P/L crosses a limit. A warning also fires
   when the open stake could push you past the loss limit.

Bets without a readable Bet365 reference, or with low read confidence, land in **Needs review**.

## Streamlit Community Cloud

- Repository: `sbachagian1101/Classform`, main file `betledger_app.py`
- Add `ANTHROPIC_API_KEY` under app **Secrets** / environment.
- The SQLite file is local to the container and is wiped on redeploy. Use **Export CSV** for backups,
  or point `DEFAULT_DB` in `betledger_store.py` at a persistent volume.

## Notes

- The app only tells you a limit is hit; it cannot block the next bet. Set a deposit limit in Bet365 too.
- Odds are stored as decimals; fractional odds in a slip are converted.
