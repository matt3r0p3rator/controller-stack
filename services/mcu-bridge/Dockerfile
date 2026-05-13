FROM python:3.12-slim

WORKDIR /app

# pyserial needs no native deps; minimalmodbus needs none either
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
