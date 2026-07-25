"""OCR Engine: Qwen3-VL через llama-server."""
import base64
import logging
import os
import time

import requests

from app.config import LLAMA_API_URL, LLAMA_HEALTH_URL, OCR_TEMPERATURE, OCR_MAX_TOKENS
from app.schemas.documents import PageResult

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = (
    "Прочитай весь текст на этом изображении документа дословно и полностью. "
    "Сохраняй структуру: заголовки, абзацы, нумерацию, списки. "
    "Таблицы передавай построчно, колонки разделяй символом |. "
    "Не пропускай строки, не сокращай и не перефразируй текст. "
    "Верни только текст без пояснений и комментариев."
)


class OCREngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = False

    def initialize(self):
        """Ждёт готовности llama-server (до 5 мин)."""
        if self._initialized:
            return
        logger.info("Ожидание llama-server...")
        for attempt in range(60):
            try:
                resp = requests.get(LLAMA_HEALTH_URL, timeout=5)
                if resp.status_code == 200:
                    logger.info("llama-server готов")
                    self._initialized = True
                    return
            except (requests.ConnectionError, requests.Timeout, OSError):
                pass
            logger.info(f"llama-server не отвечает, попытка {attempt + 1}/60...")
            time.sleep(5)
        raise RuntimeError("llama-server не запустился за 5 минут")

    def recognize_page(
        self,
        image_path: str,
        page_num: int = 1,
        temperature: float = OCR_TEMPERATURE,
        prompt: str = DEFAULT_PROMPT,
    ) -> PageResult:
        """Страница → PageResult (full_text-режим)."""
        text = self._call_image(image_path, prompt, temperature)
        return PageResult(page=page_num, text=text)

    def ocr_page_text(
        self,
        image_path: str,
        temperature: float = OCR_TEMPERATURE,
    ) -> str:
        """Страница → сырой текст (для extract-режима)."""
        return self._call_image(image_path, DEFAULT_PROMPT, temperature)

    @staticmethod
    def extract_from_text(
            pages_text: list[str],
        prompt: str,
        temperature: float = OCR_TEMPERATURE,
    ) -> str:
        """Объединяет текст страниц и делает текстовый запрос к модели."""
        combined = "\n\n".join(pages_text)
        max_chars = 60_000  # ~24K токенов для кириллицы
        if len(combined) > max_chars:
            combined = combined[:max_chars]
            logger.warning(f"Текст обрезан до {max_chars} символов")
        payload = {
            "messages": [{
                "role": "user",
                "content": f"Документ:\n\n{combined}\n\n{prompt}",
            }],
            "temperature": temperature,
            "max_tokens": OCR_MAX_TOKENS,
        }
        resp = requests.post(LLAMA_API_URL, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _call_image(image_path: str, prompt: str, temperature: float) -> str:
        """Отправляет изображение + промпт в llama-server."""
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
        payload = {
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "temperature": temperature,
            "max_tokens": OCR_MAX_TOKENS,
        }
        resp = requests.post(LLAMA_API_URL, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


engine = OCREngine()
