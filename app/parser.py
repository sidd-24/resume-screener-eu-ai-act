from pypdf import PdfReader
from pypdf.errors import PdfReadError
import io
import re


ZERO_WIDTH_CHARS = re.compile(r"[​‌‍⁠﻿]")


class CVParseError(Exception):
    """Raised when a file cannot be read as a PDF."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts all text from a PDF file given its raw bytes.
    Raises CVParseError if the file is not a readable PDF.
    """
    if not file_bytes.lstrip().startswith(b"%PDF"):
        raise CVParseError("File is not a PDF.")

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise CVParseError("PDF is password protected.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except CVParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise CVParseError(f"PDF could not be read: {e}") from e

    return clean_text(text)


def clean_text(text: str) -> str:
    """
    Removes invisible characters and collapses runs of spaces and blank lines.
    """
    text = ZERO_WIDTH_CHARS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()
