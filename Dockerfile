# Lovable Automation - Headless Browser Automation
# Using official Playwright image (includes browsers + system deps)
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY .env.example .env.example

# Create directories for persistent state
RUN mkdir -p /app/session_state /app/results

# Default environment
ENV HEADLESS=true
ENV SLOW_MO=50

# Entrypoint: CLI
ENTRYPOINT ["python", "cli.py"]

# Default command (show help)
CMD ["--help"]
