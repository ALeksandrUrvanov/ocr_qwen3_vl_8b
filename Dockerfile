FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Слой 1: Системные зависимости
# cuda-nvcc + libcublas-dev — компиляция llama.cpp (только первый запуск)
# poppler-utils + libreoffice-writer — конвертация PDF/DOCX
# curl — healthcheck в entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    cmake g++ \
    cuda-nvcc-12-6 \
    libcublas-dev-12-6 \
    libgl1 libglib2.0-0 \
    poppler-utils libreoffice-writer \
    curl \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

WORKDIR /app

# Слой 2: Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt \
    && rm -rf /root/.cache /tmp/*

# Слой 3: Код приложения
COPY app/ app/

# Слой 4: Директория для временных файлов
RUN mkdir -p storage/temp

# Слой 5: Entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# llama.cpp монтируется с хоста: -v /host/llama.cpp:/app/llama.cpp
# models монтируется с хоста:    -v /host/models:/app/models:ro
EXPOSE 8081

ENTRYPOINT ["/app/entrypoint.sh"]
