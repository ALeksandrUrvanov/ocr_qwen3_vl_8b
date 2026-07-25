"""Конвертер: PDF/DOCX/фото → PNG для OCR."""
import os
import subprocess
import tempfile
import logging
from pathlib import Path

from PIL import Image, ImageEnhance
from pdf2image import convert_from_path

from app.config import (
    PDF_DPI,
    IMAGE_MIN_SIDE,
    PREPROCESS_GRAYSCALE,
    PREPROCESS_BINARIZE,
    PREPROCESS_SHARPNESS,
)

logger = logging.getLogger(__name__)


def pdf_to_images(pdf_path: str) -> list[str]:
    output_dir = tempfile.mkdtemp(prefix="ocr_pdf_")
    images = convert_from_path(pdf_path, dpi=PDF_DPI)
    paths = []
    for i, img in enumerate(images):
        img = _preprocess_image(img)
        path = os.path.join(output_dir, f"page_{i + 1:04d}.png")
        img.save(path, "PNG", compress_level=1)
        img.close()
        paths.append(path)
    return paths


def docx_to_images(docx_path: str) -> list[str]:
    output_dir = tempfile.mkdtemp(prefix="ocr_docx_")
    logger.debug(f"Converting DOCX to PDF via LibreOffice: {docx_path}")
    try:
        subprocess.run(
            [
                "libreoffice", "--headless",
                "--convert-to", "pdf", "--outdir", output_dir,
                docx_path,
            ],
            check=True, timeout=120, capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"LibreOffice conversion timeout for {docx_path}")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"LibreOffice conversion failed: {e.stderr.decode() if e.stderr else str(e)}")
        raise
    
    pdf_name = Path(docx_path).stem + ".pdf"
    pdf_path = os.path.join(output_dir, pdf_name)
    if not os.path.isfile(pdf_path):
        raise RuntimeError(f"LibreOffice failed: {pdf_path} not created")
    return pdf_to_images(pdf_path)


def _preprocess_image(img: Image.Image) -> Image.Image:
    """Grayscale → RGB, апскейл если мелкое, резкость."""
    if PREPROCESS_GRAYSCALE or PREPROCESS_BINARIZE:
        if img.mode != "L":
            img = img.convert("L")
        if PREPROCESS_BINARIZE:
            img = img.point(lambda x: 255 if x > 127 else 0, mode="L")
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    min_side = min(w, h)
    if 0 < min_side < IMAGE_MIN_SIDE:
        scale = IMAGE_MIN_SIDE / min_side
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

    if PREPROCESS_SHARPNESS != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(PREPROCESS_SHARPNESS)

    return img


def image_to_images(image_path: str) -> list[str]:
    img = Image.open(image_path)
    img.load()
    img = _preprocess_image(img)
    output_dir = tempfile.mkdtemp(prefix="ocr_img_")
    out_path = os.path.join(output_dir, Path(image_path).stem + "_ocr.png")
    img.save(out_path, "PNG", compress_level=1)
    img.close()
    return [out_path]


def file_to_images(file_path: str) -> list[str]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return pdf_to_images(file_path)
    if ext == ".docx":
        return docx_to_images(file_path)
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}:
        return image_to_images(file_path)
    raise ValueError(f"Unsupported format: {ext}")
