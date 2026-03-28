FROM python:3.12-slim

# Install Node.js for Nansen CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm chromium \
    && rm -rf /var/lib/apt/lists/*

# Install Nansen CLI
RUN npm install -g nansen-cli

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pytest

# Copy source code
COPY *.py ./
COPY tests/ tests/
COPY skill/ skill/

# Run tests by default
CMD ["python", "-m", "pytest", "tests/", "-v"]
