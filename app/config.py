"""
Настройки проекта.

Все параметры собраны в одном месте.
Менять поведение сервиса — только здесь.
"""
import os
from pathlib import Path

# Корень проекта (папка где лежит app/)
BASE_DIR = Path(__file__).resolve().parent.parent

# llama-server (Qwen3-VL)
LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080")
LLAMA_API_URL = f"{LLAMA_SERVER_URL}/v1/chat/completions"
LLAMA_HEALTH_URL = f"{LLAMA_SERVER_URL}/health"

# Параметры инференса
OCR_TEMPERATURE = 0.1
OCR_MAX_TOKENS = 4096

# Временное хранилище (очищается после каждой задачи)
TEMP_DIR = BASE_DIR / "storage" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Допустимые форматы файлов
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".bmp",
    ".pdf", ".docx",
}

# Лимит размера файла (MB)
MAX_FILE_SIZE_MB = 200

# Сколько документов обрабатывать параллельно
MAX_CONCURRENT_TASKS = 1

# Разрешение при конвертации PDF в изображения.
# 300 — стандарт, 350–400 — лучше мелкий текст/сложные формы.
PDF_DPI = 400

# Минимальная сторона изображения для апскейла
IMAGE_MIN_SIDE = 1200

# Предобработка перед OCR
PREPROCESS_GRAYSCALE = True
PREPROCESS_BINARIZE = False
PREPROCESS_SHARPNESS = 1.25
