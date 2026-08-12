@echo off
setlocal
cd /d "%~dp0"
title Class-Only Race Analyser v4-mobile (France + Australia)

echo ==============================================
echo   Class-Only Race Analyser v4-mobile (France + Australia)
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

echo Starting app...
python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

endlocal
