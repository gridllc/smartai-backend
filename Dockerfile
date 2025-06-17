FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y git ffmpeg gcc && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Force rebuild marker
# Rebuild triggered to ensure psycopg2-binary is installed properly

# Expose port used by FastAPI
EXPOSE 10000

# Start the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]