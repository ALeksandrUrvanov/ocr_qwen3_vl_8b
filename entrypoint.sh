#!/bin/bash
set -e

LLAMA_BIN="/app/llama.cpp/build/bin/llama-server"
MODEL_DIR="/app/models"
MODEL_FILE="Qwen3VL-8B-Instruct-Q8_0.gguf"
MMPROJ_FILE="mmproj-Qwen3VL-8B-Instruct-F16.gguf"
LLAMA_PORT=8080

# -- 1. Сборка llama.cpp если ещё не собран ----------------------------------
if [ ! -f "$LLAMA_BIN" ]; then
    echo "[entrypoint] Первый запуск: собираю llama.cpp с CUDA (RTX 6000 Ada, sm_89)..."
    cd /app/llama.cpp
    cmake -B build \
        -DGGML_CUDA=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=89
    cmake --build build --config Release -j$(nproc)
    cd /app
    echo "[entrypoint] Сборка завершена"
else
    echo "[entrypoint] llama.cpp уже собран, пропускаю компиляцию"
fi

# -- 2. Поиск файлов модели --------------------------------------------------
find_model() {
    local filename="$1"
    local direct="$MODEL_DIR/$filename"
    if [ -f "$direct" ]; then
        echo "$direct"
        return
    fi
    find "$MODEL_DIR" -name "$filename" -type f 2>/dev/null | head -1
}

MODEL_PATH=$(find_model "$MODEL_FILE")
MMPROJ_PATH=$(find_model "$MMPROJ_FILE")

if [ -z "$MODEL_PATH" ]; then
    echo "[entrypoint] Ошибка: модель не найдена: $MODEL_FILE"
    exit 1
fi
if [ -z "$MMPROJ_PATH" ]; then
    echo "[entrypoint] Ошибка: mmproj не найден: $MMPROJ_FILE"
    exit 1
fi

MODEL_SIZE=$(du -sh "$MODEL_PATH" | cut -f1)
MMPROJ_SIZE=$(du -sh "$MMPROJ_PATH" | cut -f1)
echo "[entrypoint] Модель:  $MODEL_FILE ($MODEL_SIZE)"
echo "[entrypoint] Vision:  $MMPROJ_FILE ($MMPROJ_SIZE)"

# -- 3. Запуск llama-server в фоне -------------------------------------------
echo "[entrypoint] Запуск llama-server на порту $LLAMA_PORT..."
"$LLAMA_BIN" \
    -m "$MODEL_PATH" \
    --mmproj "$MMPROJ_PATH" \
    -c 32768 \
    -ngl 99 \
    --host 0.0.0.0 \
    --port "$LLAMA_PORT" \
    -np 1 \
    -fa on \
    > /tmp/llama-server.log 2>&1 &
LLAMA_PID=$!
echo "[entrypoint] llama-server PID: $LLAMA_PID"

# -- 4. Ожидание готовности llama-server -------------------------------------
echo "[entrypoint] Ожидание загрузки модели..."
ATTEMPTS=0
until curl -sf "http://localhost:$LLAMA_PORT/health" > /dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo "[entrypoint] llama-server аварийно завершился. Лог:"
        cat /tmp/llama-server.log
        exit 1
    fi
    if [ $ATTEMPTS -ge 60 ]; then
        echo "[entrypoint] Таймаут ожидания llama-server (5 мин)"
        exit 1
    fi
    sleep 5
done
echo "[entrypoint] llama-server готов (попыток: $ATTEMPTS)"

# -- 5. Запуск FastAPI --------------------------------------------------------
echo "[entrypoint] Запуск FastAPI на порту 8081..."
exec python3 -u -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8081 \
    --timeout-keep-alive 3600 \
    --timeout-graceful-shutdown 180
