FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg with ALL required libraries
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ffprobe \
    libavcodec-extra \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Verify ffmpeg installation and get version
RUN ffmpeg -version && \
    ffprobe -version && \
    which ffmpeg && \
    which ffprobe

# Set environment variables for FFmpeg paths
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV FFPROBE_PATH=/usr/bin/ffprobe
ENV PATH="/usr/bin:${PATH}"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create downloads directory with proper permissions
RUN mkdir -p downloads && chmod 777 downloads

# Environment variables for Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=10000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${PORT}/health')"

# Run application
CMD ["python", "-u", "main.py"]
