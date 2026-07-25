# OCR Qwen3-VL-8B

OCR-сервис на `Qwen3VL-8B-Instruct-Q8_0.gguf` через `llama-server` + FastAPI-обёртка с очередью.

## Stack

- Python, FastAPI, Uvicorn, Pydantic, Pillow, pdf2image, requests
- llama.cpp (`llama-server`), GGUF Qwen3-VL-8B Q8_0
- Docker, GPU; API `:8081`, llama-server внутри `:8080`

## Pipeline

1. Upload (`full_text` или `extract`) + `prompt` + `temperature`.
2. Конвертация страниц в изображения.
3. Запросы в llama-server; результат в памяти до `/result`.

## Run

```bash
# смонтировать models/ с GGUF рядом с контейнером/entrypoint
docker build -t ocr-qwen3vl .
docker run --gpus all -p 8081:8081 -v $PWD/models:/app/models ocr-qwen3vl
```

## API

- `POST /api/documents/upload` — multipart: `file`, `mode`, `prompt`, `temperature`
- `GET /api/documents/{id}/status|result`
- `GET /api/documents/queue/info`, `GET /health`

## Config

| Variable | Required | Notes |
|----------|----------|-------|
| `LLAMA_SERVER_URL` | no | default внутри контейнера |

## Notes

- GGUF и исходники llama.cpp в репозиторий не входят.
