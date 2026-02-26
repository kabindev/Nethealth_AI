@echo off
REM NetHealth AI Dashboard Launcher
REM Starts the Streamlit dashboard

echo ========================================
echo   NetHealth AI Dashboard
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "src\dashboard\app.py" (
    echo ERROR: Please run this script from the NetHealth_AI directory
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Starting dashboard...
echo.
echo The dashboard will open in your browser at:
echo   http://localhost:8501
echo.
echo Press Ctrl+C to stop the dashboard
echo ========================================
echo.

REM Run Streamlit
python -m streamlit run src\dashboard\app.py

REM If streamlit fails, try alternative method
if errorlevel 1 (
    echo.
    echo Failed to start with 'python -m streamlit'
    echo Trying alternative method...
    streamlit run src\dashboard\app.py
)

pause
