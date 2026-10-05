# Use Microsoft's official Playwright Python image (includes pre-installed Chromium, Firefox, WebKit and OS dependencies)
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Set environment variables for Python & Playwright
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /workspace

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure storage directory exists
RUN mkdir -p storage/uploaded storage/extracted storage/chunks storage/evidence storage/test_cases

# Expose API port
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
