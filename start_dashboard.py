"""
Quick Dashboard Launcher

Python script to start the NetHealth AI dashboard.
Works on all platforms (Windows, Linux, Mac).
"""

import os
import sys
import subprocess
from pathlib import Path


def main():
    """Launch the Streamlit dashboard"""
    
    print("=" * 50)
    print("  NetHealth AI Dashboard")
    print("=" * 50)
    print()
    
    # Check if we're in the right directory
    dashboard_path = Path("src/dashboard/app.py")
    if not dashboard_path.exists():
        print("ERROR: Please run this script from the NetHealth_AI directory")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    
    print("Starting dashboard...")
    print()
    print("The dashboard will open in your browser at:")
    print("  http://localhost:8501")
    print()
    print("Press Ctrl+C to stop the dashboard")
    print("=" * 50)
    print()
    
    # Try to run Streamlit
    try:
        # Method 1: python -m streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", str(dashboard_path)
        ], check=True)
    except subprocess.CalledProcessError:
        print()
        print("Failed to start with 'python -m streamlit'")
        print("Trying alternative method...")
        try:
            # Method 2: streamlit command directly
            subprocess.run([
                "streamlit", "run", str(dashboard_path)
            ], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print()
            print("ERROR: Could not start Streamlit")
            print()
            print("Please install Streamlit:")
            print("  pip install streamlit")
            sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("Dashboard stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
