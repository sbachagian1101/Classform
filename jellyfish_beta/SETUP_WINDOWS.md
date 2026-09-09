# Setting up on Windows

## 1. Clone

Open PowerShell or Command Prompt and run:

```bat
mkdir "D:\01_PREDICTION MODELS" 2>nul
cd /d "D:\01_PREDICTION MODELS"
git clone --branch claude/jellyfish-bloom-mauritius-model-xyzofl https://github.com/sbachagian1101/Classform.git jellyfish
cd jellyfish\jellyfish_beta
```

You need Git for Windows (https://git-scm.com) and Python 3.11 to 3.13 with
"Add Python to PATH" ticked. The Classform repository is cloned as a whole;
the jellyfish project is the `jellyfish_beta` folder inside it.

## 2. Run

Double-click `run.bat` in `jellyfish_beta`, or run it from the prompt. On the
first run it will:

1. create a local `.venv` and install the requirements;
2. download weather and marine history from Open-Meteo for all 28 beaches
   since January 2022 (a few minutes, no account needed);
3. score the coming week and write `data\outputs\latest_risk.csv`;
4. print validation metrics against the Mauritian event table;
5. open the Streamlit dashboard in your browser.

If the download fails, it falls back to synthetic data so the app still opens.
The Open-Meteo fetchers were written without live testing, so a small fix may
be needed on the first real pull; the error will name the field.

Later runs skip the history download. Delete `data\features\daily_features.csv`
to force a refresh.

## 3. Individual commands

From `jellyfish_beta` with the venv active (`.venv\Scripts\activate`):

```bat
python -m pytest tests -q
python scripts\build_features.py --source openmeteo --start 2012-01-01
python scripts\run_forecast.py --days 7
python scripts\validate.py --events data\events\mru_events.csv --min-confidence medium --tune
python scripts\harvest_press.py
python -m streamlit run app.py
```

Pull history back to 2012 if you want the validator to see every dated event
in the table; the Open-Meteo marine archive may only reach back to about
2021, in which case wave and current features are empty before that and the
Physalia index falls back to wind only.

## 4. Updating from GitHub

```bat
cd /d "D:\01_PREDICTION MODELS\jellyfish"
git pull
```
