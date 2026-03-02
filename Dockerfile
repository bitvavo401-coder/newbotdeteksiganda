FROM python:3.11-slim

WORKDIR /app

# Debug: Lihat isi direktori setelah copy
COPY . .
RUN ls -la && pwd

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Cek apakah main.py ada
RUN if [ ! -f main.py ]; then \
    echo "Error: main.py tidak ditemukan!"; \
    ls -la; \
    exit 1; \
    fi

# Jalankan bot
CMD ["python", "main.py"]
