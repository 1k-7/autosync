# Use a lightweight and secure Python base image
FROM python:3.11-slim-bullseye

# Set the working directory for the application
WORKDIR /app

# Update packages and install git (sometimes required by specific pip packages)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker's layer caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project code into the working directory
COPY . .

# Start the routing engine directly
CMD ["python3", "bot.py"]