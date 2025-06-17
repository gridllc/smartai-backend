# Use official lightweight Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (git and ffmpeg needed)
RUN apt-get update && \
    apt-get install -y git ffmpeg gcc && \
    apt-get clean

# Set work directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Expose the port used by uvicorn
EXPOSE 10000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
