FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (including graphviz)
RUN apt-get update && apt-get install -y \
    build-essential \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements/base.txt .
RUN pip install --no-cache-dir -r base.txt
RUN pip install graphviz

# Copy source code and data
COPY src/ src/
COPY data/ data/
COPY .env.example .env

# Expose Streamlit port
EXPOSE 8501

# Set python path
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Command to run the app
CMD ["streamlit", "run", "src/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
