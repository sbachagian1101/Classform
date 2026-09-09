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
    echo First run: downloading weather and marine history from Open-Meteo since 2012.
    echo One line per beach as it completes. Each beach-year is cached, so if the
    echo Open-Meteo free quota runs out the script waits for the next hour, and a
    echo rerun resumes where it stopped.
    echo.
    python scripts\build_features.py --source openmeteo --start 2012-01-01
    if errorlevel 1 (
        echo.
        echo ***********************************************************************
        echo  HISTORY DOWNLOAD FAILED. Read the error above and report it.
        echo  If it mentions a daily quota, rerun tomorrow: progress is cached.
        echo  Validation will be skipped. The forecast below is still live.
        echo ***********************************************************************
        echo.
        pause
    )
)

echo.
echo Scoring the coming week...
python scripts\run_forecast.py --days 7
if errorlevel 1 (
    echo.
    echo ***********************************************************************
    echo  LIVE FORECAST FAILED. Read the error above and report it.
    echo  Opening the app on synthetic data so you can still see the layout.
    echo ***********************************************************************
    echo.
    pause
    if not exist "data\raw\synthetic_hourly.csv" python scripts\make_synthetic.py
    python scripts\run_forecast.py --source synthetic
)

if exist "data\features\daily_features.csv" (
    echo.
    echo Validating priors against the Mauritian event table (medium confidence and above)...
    python scripts\validate.py --events data\events\mru_events.csv --min-confidence medium --tune
    echo.
)

echo Starting app...
python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

endlocal
