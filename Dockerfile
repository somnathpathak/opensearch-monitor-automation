FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY scripts/ scripts/

# Entrypoint
ENTRYPOINT ["python", "scripts/manage_monitors.py"]
