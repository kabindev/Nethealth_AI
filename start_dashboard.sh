#!/bin/bash
# NetHealth AI Dashboard Launcher
# Starts the Streamlit dashboard

echo "========================================"
echo "  NetHealth AI Dashboard"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -f "src/dashboard/app.py" ]; then
    echo "ERROR: Please run this script from the NetHealth_AI directory"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo "Starting dashboard..."
echo ""
echo "The dashboard will open in your browser at:"
echo "  http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo "========================================"
echo ""

# Run Streamlit
python -m streamlit run src/dashboard/app.py

# If that fails, try alternative method
if [ $? -ne 0 ]; then
    echo ""
    echo "Failed to start with 'python -m streamlit'"
    echo "Trying alternative method..."
    streamlit run src/dashboard/app.py
fi
