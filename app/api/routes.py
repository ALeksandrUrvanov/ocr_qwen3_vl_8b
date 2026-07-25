"""HTTP-эндпоинты: upload → status → result."""
import logging
import uuid
import shutil
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.config import TEMP_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
from app.core.queue import task_queue
from app.schemas.documents import (
    DocumentResult,
    OCRMode,
    OCRSettings,
    TaskStatus,
    UploadResponse,
    StatusResponse,
    QueueInfoResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _sanitize_filename(filename: str) -> str:
    filename = Path(filename).name
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '_', filename)
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    return filename


async def _save_and_queue(file: UploadFile, settings: OCRSettings) -> tuple[str, str, int]:
    """Валидация, сохранение файла, постановка в очередь."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    safe_filename = _sanitize_filename(file.filename)
    ext = Path(safe_filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Rejected file with unsupported extension: {ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Format '{ext}' not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    task_id = uuid.uuid4().hex[:12]
    task_dir = TEMP_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    file_path = task_dir / safe_filename

    size = 0
    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    logger.warning(f"[{task_id}] File too large: {size / 1024 / 1024:.2f} MB")
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max: {MAX_FILE_SIZE_MB} MB",
                    )
                f.write(chunk)
    except Exception as e:
        shutil.rmtree(task_dir, ignore_errors=True)
        logger.error(f"[{task_id}] Upload failed: {e}")
        raise

    task_queue.add_task(task_id, safe_filename, settings)
    logger.info(f"[{task_id}] Загружен: {safe_filename} ({size / 1024 / 1024:.2f} MB)")
    return task_id, safe_filename, size


@router.get("/queue/info", response_model=QueueInfoResponse)
async def queue_info():
    """Информация об очереди и памяти."""
    return task_queue.get_queue_info()


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    mode: OCRMode = Form(
        OCRMode.full_text,
        description="full_text — полный текст постранично. extract — извлечение сущностей, один JSON.",
    ),
    prompt: Optional[str] = Form(None, description="Промпт для модели (обязательно)."),
    temperature: Optional[float] = Form(None, description="Температура генерации (0.0–2.0, например 0.1)."),
):
    """
    Загрузить документ (PDF/DOCX/PNG/JPG/TIFF/BMP, до 200 MB).

    - `full_text` — полный текст постранично
    - `extract` — извлечение сущностей, один JSON на документ
    """
    missing = [f for f, v in (("prompt", prompt), ("temperature", temperature)) if v is None]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Заполните обязательные параметры: {', '.join(missing)}",
        )
    settings = OCRSettings.model_validate({"mode": mode, "prompt": prompt, "temperature": temperature})
    task_id, filename, size = await _save_and_queue(file, settings)
    return UploadResponse(
        task_id=task_id,
        filename=filename,
        size_mb=round(size / 1024 / 1024, 2),
        status="queued",
    )


@router.get("/{task_id}/status", response_model=StatusResponse)
async def get_status(task_id: str):
    """Статус задачи и прогресс по страницам."""
    result = task_queue.get_result(task_id)
    if result is None:
        logger.warning(f"Status request for unknown task: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")

    return StatusResponse(
        task_id=result.task_id,
        filename=result.filename,
        status=result.status,
        total_pages=result.total_pages,
        processed_pages=result.processed_pages,
    )


@router.get("/{task_id}/result", response_model=DocumentResult)
async def get_result(task_id: str):
    """Результат задачи. После выдачи удаляется из памяти."""
    result = task_queue.get_result(task_id)
    if result is None:
        logger.warning(f"Result request for unknown task: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")

    if result.status == TaskStatus.queued:
        raise HTTPException(status_code=202, detail="Task is queued")

    if result.status == TaskStatus.processing:
        raise HTTPException(
            status_code=202,
            detail=f"Processing: {result.processed_pages}/{result.total_pages}",
        )

    if result.status == TaskStatus.failed:
        error = result.error
        task_queue.pop_result(task_id)
        logger.error(f"[{task_id}] Result request for failed task: {error}")
        raise HTTPException(status_code=500, detail=error)

    final = task_queue.pop_result(task_id)
    logger.info(f"[{task_id}] Результат выдан")
    return final
