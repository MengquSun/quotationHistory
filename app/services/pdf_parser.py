from __future__ import annotations

import io


def extract_text_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires pypdf. Install project requirements first.") from exc

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("Scanned/OCR PDFs are not supported yet. Please upload a selectable-text PDF.")
    return text
