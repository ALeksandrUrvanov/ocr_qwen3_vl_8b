"""Очередь задач: upload → OCR → результат в памяти → выдача → очистка."""
import json
import logging
import threading
import time
import traceback
from collections import deque

from app.config import TEMP_DIR, MAX_CONCURRENT_TASKS
from app.schemas.documents import DocumentResult, OCRMode, OCRSettings, PageResult, TaskStatus
from app.core.ocr_engine import engine
from app.core.converter import file_to_images
from app.core.cleanup import full_cleanup

logger = logging.getLogger(__name__)


def _normalize_extract_json_quotes(text: str) -> str:
    """В JSON от модели заменяем двойные кавычки внутри строковых значений на одинарные."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return text
        for key, val in data.items():
            if isinstance(val, str):
                data[key] = val.replace('"', "'")
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


class TaskQueue:
    def __init__(self):
        self._queue: deque[str] = deque()
        self._results: dict[str, DocumentResult] = {}
        self._settings: dict[str, OCRSettings] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)
        self._running = False
        self._active_workers: set[threading.Thread] = set()
        self._workers_lock = threading.Lock()

    def start(self):
        engine.initialize()
        self._running = True
        thread = threading.Thread(target=self._dispatcher, daemon=False, name="TaskDispatcher")
        thread.start()
        logger.info(f"Очередь запущена (макс. задач: {MAX_CONCURRENT_TASKS})")

    def stop(self):
        """Graceful shutdown: ждёт завершения активных задач."""
        logger.info("Остановка очереди...")
        self._running = False

        with self._workers_lock:
            active = list(self._active_workers)

        if active:
            logger.info(f"Ожидание завершения {len(active)} активных задач...")
            for worker in active:
                worker.join(timeout=60)
                if worker.is_alive():
                    logger.warning(f"Задача {worker.name} не завершилась вовремя")

        logger.info("Очередь остановлена")

    def add_task(self, task_id: str, filename: str, settings: OCRSettings):
        with self._lock:
            self._results[task_id] = DocumentResult(
                task_id=task_id, filename=filename, status=TaskStatus.queued
            )
            self._settings[task_id] = settings
            self._queue.append(task_id)

    def get_result(self, task_id: str) -> DocumentResult | None:
        with self._lock:
            return self._results.get(task_id)

    def pop_result(self, task_id: str) -> DocumentResult | None:
        with self._lock:
            return self._results.pop(task_id, None)

    def get_queue_info(self) -> dict:
        with self._lock:
            return {"queued": len(self._queue), "active_results": len(self._results)}

    def _dispatcher(self):
        while self._running:
            task_id = None
            with self._lock:
                if self._queue:
                    task_id = self._queue.popleft()
            if task_id is None:
                time.sleep(0.5)
                continue
            self._semaphore.acquire()
            thread = threading.Thread(
                target=self._process_task,
                args=(task_id,),
                daemon=False,
                name=f"Worker-{task_id}",
            )
            with self._workers_lock:
                self._active_workers.add(thread)
            thread.start()

    def _process_task(self, task_id: str):
        task_dir = str(TEMP_DIR / task_id)
        temp_images = []
        try:
            with self._lock:
                result = self._results[task_id]
                result.status = TaskStatus.processing
                settings = self._settings.pop(task_id)

            file_path = str(TEMP_DIR / task_id / result.filename)
            logger.info(
                f"[{task_id}] Начало: {result.filename} "
                f"(mode={settings.mode.value}, t={settings.temperature})"
            )
            temp_images = file_to_images(file_path)
            with self._lock:
                result.total_pages = len(temp_images)

            all_pages = []
            task_start = time.time()

            if settings.mode == OCRMode.extract:
                if len(temp_images) == 1:
                    full_text = engine.recognize_page(
                        temp_images[0],
                        prompt=settings.prompt,
                        temperature=settings.temperature,
                    ).text
                    with self._lock:
                        result.processed_pages = 1
                else:
                    # OCR каждой страницы → extract из объединённого текста
                    pages_text = []
                    for i, img_path in enumerate(temp_images):
                        text = engine.ocr_page_text(img_path, settings.temperature)
                        pages_text.append(text)
                        with self._lock:
                            result.processed_pages = i + 1
                    full_text = engine.extract_from_text(
                        pages_text,
                        prompt=settings.prompt,
                        temperature=settings.temperature,
                    )
                all_pages = [PageResult(page=1, text=full_text)]
            else:
                # full_text: каждая страница отдельно
                for i, img_path in enumerate(temp_images):
                    page_result = engine.recognize_page(
                        img_path,
                        page_num=i + 1,
                        temperature=settings.temperature,
                        prompt=settings.prompt,
                    )
                    all_pages.append(page_result)
                    with self._lock:
                        result.processed_pages = i + 1
                full_text = "\n\n".join(
                    f"--- Страница {p.page} ---\n{p.text}" for p in all_pages
                )
            if settings.mode == OCRMode.extract:
                full_text = _normalize_extract_json_quotes(full_text)
            with self._lock:
                result.pages = all_pages
                result.full_text = full_text
                result.status = TaskStatus.completed

            elapsed = time.time() - task_start
            logger.info(f"[{task_id}] Завершено: {len(temp_images)} стр., {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"[{task_id}] Failed: {e}")
            logger.error(traceback.format_exc())
            with self._lock:
                if task_id in self._results:
                    self._results[task_id].status = TaskStatus.failed
                    self._results[task_id].error = str(e)
        finally:
            full_cleanup(task_dir, temp_images)
            self._semaphore.release()
            with self._workers_lock:
                self._active_workers.discard(threading.current_thread())


task_queue = TaskQueue()
