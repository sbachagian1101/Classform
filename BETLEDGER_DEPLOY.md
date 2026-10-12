# BetLedger — screenshot-driven betting ledger

Logs Bet365 bets from screenshots (no account access, no scraping), works out
profit/loss per bet, and alerts when a daily win or loss limit is hit.

## Files

- `betledger_app.py` — Streamlit UI
- `betledger_store.py` — SQLite ledger, daily maths, limit alerts
- `betledger_reader.py` — screenshot → bets (Claude vision, Tesseract fallback, text parser)
- `betledger_watch.py` — live screen watcher (runs on your PC)
- `run_betledger.bat` — Windows one-click: watcher + app
- `tests/test_betledger.py`, `tests/test_betledger_watch.py`

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # for the Claude vision reader (recommended)
# or, for local-only OCR: install tesseract and `pip install pytesseract pillow`
streamlit run betledger_app.py
```

## Automatic mode: the screen watcher

`betledger_watch.py` runs on the PC where you use Bet365 (website or desktop app).
Every few seconds it grabs the screen; when a Bet365 window is in front and the
picture has changed it runs the frame through the reader and writes bets and
balance into the ledger. Limit alerts pop up as desktop notifications and in the app.

```bash
pip install -r requirements.txt            # includes mss, plyer (+ pygetwindow on Windows)
export ANTHROPIC_API_KEY=sk-ant-...
python betledger_watch.py                  # watches only while a Bet365 window is active
python betledger_watch.py --always         # macOS/Linux without window titles: watch everything
```

On Windows `run_betledger.bat` starts the watcher and the app together.
Turn on **Live refresh** in the app sidebar so the dashboard follows the watcher.

What it cannot do: a hosted Streamlit page can never see your screen (browsers forbid it),
so the watcher must run locally. Phones: Android could run a capture service but that is a
separate build; iPhone cannot capture in the background, so use the screenshot upload there.
Bets only get logged when they appear on screen, so open **My Bets** after a settlement.

## Daily workflow (manual fallback)

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
