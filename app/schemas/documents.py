"""Pydantic-схемы для API."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class OCRMode(str, Enum):
    full_text = "full_text"
    extract = "extract"


class OCRSettings(BaseModel):
    """Настройки распознавания, передаются клиентом при загрузке."""
    mode: OCRMode = Field(
        OCRMode.full_text,
        description=(
            "full_text — полный текст постранично (--- Страница N ---). "
            "extract — извлечение сущностей, один ответ на весь документ."
        ),
    )
    prompt: str = Field(
        ...,
        description="Промпт для модели (обязательно).",
    )
    temperature: float = Field(
        ...,
        ge=0.0,
        le=2.0,
        description="Температура генерации (0.0–2.0, например 0.1).",
    )


class PageResult(BaseModel):
    """Результат обработки одной страницы."""
    page: int = Field(..., description="Номер страницы")
    text: str = Field(default="", description="Распознанный текст / ответ модели")


class DocumentResult(BaseModel):
    """Полный результат обработки документа."""
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int = 0
    processed_pages: int = 0
    pages: list[PageResult] = []
    full_text: str = ""
    error: Optional[str] = None


class UploadResponse(BaseModel):
    """Ответ на загрузку документа."""
    task_id: str = Field(..., description="ID задачи для отслеживания")
    filename: str = Field(..., description="Имя загруженного файла")
    size_mb: float = Field(..., description="Размер файла в MB")
    status: str = Field(default="queued", description="Начальный статус")


class StatusResponse(BaseModel):
    """Ответ на запрос статуса."""
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int = Field(default=0, description="Всего страниц в документе")
    processed_pages: int = Field(default=0, description="Обработано страниц")


class QueueInfoResponse(BaseModel):
    """Информация об очереди."""
    queued: int = Field(..., description="Задач в очереди")
    active_results: int = Field(..., description="Активных результатов в памяти")
