@echo off
REM Quick Setup Script for NetHealth AI Validation

echo ========================================
echo NetHealth AI - Validation Setup
echo ========================================
echo.

echo Step 1: Generating synthetic data...
echo This will create 1000+ fault scenarios with 120 time points each
python src\utils\data_generator.py --scenarios 1000 --points 120 --validate

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Data generation failed!
    pause
    exit /b 1
)

echo.
echo Step 2: Running validation tests...
echo This will test diagnosis accuracy and generate metrics
python tests\run_validation.py

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Validation failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS! Validation setup complete
echo ========================================
echo.
echo Generated files:
echo   - data/synthetic/metrics_extended.csv
echo   - data/synthetic/ground_truth.json
echo   - outputs/VALIDATION_METRICS.json
echo   - outputs/confusion_matrix.png
echo.
echo You can now run the dashboard to see:
echo   1. System Performance tab with accuracy metrics
echo   2. Bayesian probability distributions
echo   3. Granger causality proof
echo.
echo Run: streamlit run src\dashboard\app.py
echo.
pause
