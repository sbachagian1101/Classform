@echo off
setlocal
cd /d "%~dp0"
title Mauritius Jellyfish Risk (beta)

echo ==============================================
echo   Mauritius Jellyfish Risk (beta)
echo ==============================================
echo.

where py >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python was not found.
        echo Install Python 3.11, 3.12 or 3.13 from python.org and tick "Add Python to PATH".
        pause
        exit /b 1
    )
    set "PY_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Checking dependencies...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies. Check your internet connection and try again.
    pause
    exit /b 1
)

if not exist "data\features\daily_features.csv" (
    echo.
    echo First run: downloading weather and marine history from Open-Meteo since 2022.
    echo This takes a few minutes for 28 beaches. Press Ctrl+C to skip and use synthetic data instead.
    echo.
    python scripts\build_features.py --source openmeteo --start 2022-01-01
    if errorlevel 1 (
        echo.
        echo History download failed. Falling back to a synthetic dry run so the app still opens.
        python scripts\make_synthetic.py
        python scripts\build_features.py --source synthetic
    )
)

echo.
echo Scoring the coming week...
python scripts\run_forecast.py --days 7
if errorlevel 1 (
    echo Live forecast failed. Using the synthetic tail so the app still opens.
    if not exist "data\raw\synthetic_hourly.csv" python scripts\make_synthetic.py
    python scripts\run_forecast.py --source synthetic
)

echo.
echo Validating priors against the Mauritian event table (medium confidence and above)...
python scripts\validate.py --events data\events\mru_events.csv --min-confidence medium
echo.

echo Starting app...
python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

endlocal
