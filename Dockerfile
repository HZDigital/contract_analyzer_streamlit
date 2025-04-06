FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/src/

# Create results directory
RUN mkdir -p /app/results

# Set environment variables
ENV PYTHONPATH=/app

# Expose Streamlit port
EXPOSE 8501

# Command to run the app
CMD ["streamlit", "run", "src/contract_analyzer_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
