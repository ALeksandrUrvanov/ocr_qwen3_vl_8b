"""
Пример вызова OCR API.

Схема: POST /api/documents/upload (file, mode, prompt, temperature) → task_id
       → GET .../status до status=completed → GET .../result → full_text.

Состояние очереди: GET /api/documents/queue/info → queued, active_results.

Режимы: full_text — постраничный текст; extract — один JSON на документ.
Переключение: задать PROMPT = PROMPT_FULL_TEXT или PROMPT_EXTRACT (и тогда mode подставится автоматически).
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8081"
FILE_PATH = "test_1.pdf"
TEMPERATURE = 0.1

PROMPT_FULL_TEXT = (
    "Прочитай весь текст на этом изображении документа дословно и полностью. "
    "Сохраняй структуру: заголовки, абзацы, нумерацию, списки. "
    "Таблицы передавай построчно, колонки разделяй символом |. "
    "Не пропускай строки, не сокращай и не перефразируй текст. "
    "Верни только текст без пояснений и комментариев."
)
PROMPT_EXTRACT = """Проанализируй документ (счёт, акт, УПД, счёт-фактура).
Извлеки данные и верни ТОЛЬКО JSON без пояснений:

{
  "contractor": "Продавец — организация, выставившая счёт (поле Продавец, НЕ Покупатель)",
  "description": "Краткое описание услуги/товара",
  "amount": "Итоговая сумма к оплате в формате числа, разделитель копеек — точка (например 8746.40)",
  "date": "Дата документа"
}

Если поле не найдено — укажи null.
Внутри значений строк используй только одинарные кавычки (апострофы), например: ООО 'СЕНСУ', не двойные и не экранированные.
Верни ТОЛЬКО JSON, без markdown, без комментариев."""

# PROMPT задаёт режим: full_text или extract
PROMPT = PROMPT_FULL_TEXT
#PROMPT = PROMPT_EXTRACT


def main():
    path = Path(FILE_PATH)
    if not path.is_file():
        print(f"Файл не найден: {path}")
        sys.exit(1)

    r = requests.get(f"{BASE_URL}/api/documents/queue/info", timeout=5)
    if r.status_code == 200:
        info = r.json()
        print(f"Очередь: {info.get('queued', 0)} в ожидании, {info.get('active_results', 0)} активных")

    mode = "extract" if PROMPT is PROMPT_EXTRACT else "full_text"
    data: dict = {"temperature": TEMPERATURE, "mode": mode, "prompt": PROMPT}

    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/documents/upload",
            files={"file": (path.name, f)},
            data=data,
            timeout=60,
        )
    if resp.status_code != 202:
        print(f"Ошибка загрузки {resp.status_code}: {resp.text}")
        sys.exit(1)

    task_id = resp.json()["task_id"]

    start = time.time()
    while True:
        r = requests.get(f"{BASE_URL}/api/documents/{task_id}/status", timeout=10)
        data = r.json()
        status = data["status"]

        if status == "completed":
            elapsed = time.time() - start
            print(f"Готово: {data['processed_pages']} стр. за {elapsed:.1f}s")
            break
        if status == "failed":
            print("Ошибка обработки")
            sys.exit(1)

        print(f"Обработка: {data.get('processed_pages', 0)}/{data.get('total_pages', '?')} стр.", end="\r")
        time.sleep(2)

    r = requests.get(f"{BASE_URL}/api/documents/{task_id}/result", timeout=60)
    if r.status_code != 200:
        print(f"Ошибка результата {r.status_code}: {r.text}")
        sys.exit(1)

    full_text = r.json().get("full_text", "")
    out = path.with_suffix(".txt")
    try:
        full_text = json.dumps(json.loads(full_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        pass
    out.write_text(full_text, encoding="utf-8")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
