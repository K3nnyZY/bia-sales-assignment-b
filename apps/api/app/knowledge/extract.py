"""Bounded extraction process: UTF-8 or text-only PDFs, no OCR or active content."""

import io
import json
import re
import sys
import unicodedata

from pypdf import PdfReader

MAX_BYTES = 2 * 1024 * 1024
MAX_CHARS = 100_000


class ExtractionError(ValueError):
    pass


def safe_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Cf")
    check = normalized.casefold()
    patterns = [
        r"(ignore|disregard|override|forget).{0,80}(instruction|prompt|policy|permission|rule)",
        r"(ignora|omite|olvida|anula|ignorar).{0,80}(instrucci|regla|permiso|pol[ií]tica)",
        r"(system\s*prompt|developer\s*message|<\|im_start\|>|\[inst\]|<system>)",
        r"(grant|elevate|bypass|concede|otorga|eleva).{0,80}(permission|privileg|permiso|acceso)",
        r"(act as|act[uú]a como|cambia tu rol|revela.{0,20}(clave|secreto))",
    ]
    if any(re.search(p, check, re.S) for p in patterns):
        raise ExtractionError("UNSAFE_INSTRUCTIONS")
    if "\x00" in normalized:
        raise ExtractionError("INVALID_TEXT")
    return normalized


def extract(data: bytes, extension: str) -> str:
    if not data or len(data) > MAX_BYTES:
        raise ExtractionError("FILE_SIZE")
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ExtractionError("INVALID_PDF")
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
            raise ExtractionError("PDF_LIMIT")
        pages = []
        for page in reader.pages:
            stream = page.get_contents()
            if stream and len(stream.get_data()) > MAX_BYTES:
                raise ExtractionError("PDF_LIMIT")
            pages.append(page.extract_text() or "")
            if sum(map(len, pages)) > MAX_CHARS:
                raise ExtractionError("TEXT_LIMIT")
        value = "\n\n".join(pages)
    elif extension in {".txt", ".md"}:
        value = data.decode("utf-8-sig", errors="strict")
    else:
        raise ExtractionError("UNSUPPORTED_FORMAT")
    if not value.strip() or len(value) > MAX_CHARS:
        raise ExtractionError("EMPTY_OR_LARGE_TEXT")
    return safe_text(value)


def chunks(value: str) -> list[tuple[int, int, str]]:
    return [
        (start, min(start + 900, len(value)), value[start : start + 900])
        for start in range(0, len(value), 780)
        if value[start : start + 900].strip()
    ]


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        # Linux only; macOS address-space limits differ.
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        print(json.dumps({"text": extract(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1])}))
    except Exception as exc:
        print(
            json.dumps(
                {"error": str(exc) if isinstance(exc, ExtractionError) else "EXTRACTION_FAILED"}
            )
        )
