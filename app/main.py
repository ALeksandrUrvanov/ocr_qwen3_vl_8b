"""Точка входа FastAPI. Логирование настраивается до импортов."""
import sys
import logging
import datetime

# Отключаем буферизацию для stdout
sys.stdout.reconfigure(line_buffering=True)


class MoscowFormatter(logging.Formatter):
    """Время МСК (UTC+3)."""
    MSK = datetime.timezone(datetime.timedelta(hours=3))

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.datetime.fromtimestamp(record.created, tz=self.MSK)
        return dt.strftime('%Y-%m-%d %H:%M:%S')


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(MoscowFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [handler]

logger = logging.getLogger(__name__)


class EndpointFilter(logging.Filter):
    """Скрывает частые запросы (status, queue/info, health) из access-лога uvicorn."""
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not (
            ('GET /api/documents/' in message and '/status' in message) or
            ('GET /api/documents/queue/info' in message) or
            ('GET /health' in message)
        )


logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from app.core.queue import task_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск сервиса...")
    task_queue.start()
    logger.info("Сервис запущен")
    yield
    logger.info("Остановка сервиса...")
    task_queue.stop()
    logger.info("Сервис остановлен")


app = FastAPI(
    title="OCR Service — Qwen3-VL",
    description="PDF/DOCX/фото → текст. Модель: Qwen3-VL-8B через llama.cpp.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health():
    """Проверка что сервер работает."""
    info = task_queue.get_queue_info()
    return {"status": "ok", **info}
