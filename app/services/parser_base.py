"""Base parser interfaces for PaperLens."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class PdfParser(ABC):
    name: str

    @classmethod
    def is_available(cls) -> bool:
        return True

    @abstractmethod
    def parse(self, pdf_path: Path) -> Dict[str, Any]:
        raise NotImplementedError
