# Use Python 3.10 slim base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg git build-essential libpq-dev && \
    apt-get clean

# Copy only requirements first for better caching
COPY requirements.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Optional: Copy .env file if it exists (uncomment if you're sure it’s available during build)
# COPY .env .env

# Expose the app port
EXPOSE 10000

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]