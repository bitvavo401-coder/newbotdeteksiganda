FROM python:3.11-slim

WORKDIR /app

# Salin file requirements terlebih dahulu untuk memanfaatkan caching Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode aplikasi
COPY . .

# Set environment variable untuk memastikan log Python langsung ditampilkan
ENV PYTHONUNBUFFERED=1

# Perintah untuk menjalankan bot
CMD ["python", "main.py"]
