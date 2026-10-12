@echo off
REM Starts the BetLedger app and the screen watcher side by side.
REM Set your key first:  setx ANTHROPIC_API_KEY sk-ant-...   (then reopen this window)
pip install -r requirements.txt
start "BetLedger watcher" cmd /k python betledger_watch.py
streamlit run betledger_app.py
