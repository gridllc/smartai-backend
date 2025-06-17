# Use official Python slim image
FROM python:3.10-slim

# Install ffmpeg for audio extraction
RUN apt-get update && apt-get install -y ffmpeg

# Set working directory inside the container
WORKDIR /app

# Copy everything from host to container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Expose the port your FastAPI app will use
EXPOSE 10000

# Start the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

