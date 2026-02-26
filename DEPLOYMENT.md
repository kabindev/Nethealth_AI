# Deployment Guide

## Prerequisites
*   Docker installed
*   Git installed

## Build and Run with Docker

1.  **Build the Image**
    ```bash
    docker build -f deployment/Dockerfile -t belden-one-view .
    ```

2.  **Run the Container**
    ```bash
    docker run -p 8501:8501 belden-one-view
    ```

3.  **Access the Dashboard**
    Open your browser to `http://localhost:8501`.

## Local Development (Without Docker)

1.  **Install Dependencies**
    ```bash
    pip install -r requirements/base.txt
    pip install graphviz  # Requires Graphviz system binary
    ```

2.  **Run Streamlit**
    ```bash
    streamlit run src/dashboard/app.py
    ```
