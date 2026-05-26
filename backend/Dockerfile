FROM python:3.12-slim

WORKDIR /app

# Install C compiler for SNN library
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build compiled SNN library (Million Compiler generated C code)
RUN gcc -shared -O3 -o snn/lib/snn_trader.so snn/lib/snn_trader.c -lm

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8080"]