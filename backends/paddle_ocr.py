from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from ..runtime import configure_runtime
from .base import BackendMixin
from .common import PaddleOCR


class PaddleOCREngine(BackendMixin):
    def __init__(self, lang: str = "en") -> None:
        super().__init__()
        configure_runtime()
        self.lang = lang
        self.model = None
        if PaddleOCR is None:
            self.error = "PaddleOCR is not installed"
            return
        try:
            self.model = PaddleOCR(
                lang=lang,
                device="cpu",
                enable_hpi=False,
                enable_mkldnn=False,
                cpu_threads=2,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.model is not None

    def recognize(self, image_path: str | Path, crop_box_xyxy: Optional[List[float]] = None) -> Dict[str, Any]:
        if self.model is None:
            return {"engine": "paddleocr", "text": None, "confidence": 0.0, "lines": [], "error": self.error}

        image_path = str(image_path)
        if crop_box_xyxy:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                x0, y0, x1, y1 = [int(round(v)) for v in crop_box_xyxy]
                crop = image.crop((max(0, x0), max(0, y0), min(image.width, x1), min(image.height, y1)))
                result = self.model.predict(np.asarray(crop))
        else:
            result = self.model.predict(image_path)

        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        confidences: List[float] = []

        for item in result:
            item_json = item.json if hasattr(item, "json") else None
            data = item_json if isinstance(item_json, dict) else None
            rec_texts = []
            rec_scores = []
            rec_polys = []
            if data:
                rec_texts = data.get("rec_texts") or []
                rec_scores = data.get("rec_scores") or []
                rec_polys = data.get("rec_polys") or []
            elif isinstance(item, dict):
                rec_texts = item.get("rec_texts") or []
                rec_scores = item.get("rec_scores") or []
                rec_polys = item.get("rec_polys") or []

            for idx, text in enumerate(rec_texts):
                score = float(rec_scores[idx]) if idx < len(rec_scores) else 0.0
                poly = rec_polys[idx] if idx < len(rec_polys) else None
                text = str(text).strip()
                if not text:
                    continue
                lines.append({"text": text, "score": score, "polygon": poly})
                texts.append(text)
                confidences.append(score)

        return {
            "engine": "paddleocr",
            "text": " ".join(texts).strip() or None,
            "confidence": max(confidences) if confidences else 0.0,
            "lines": lines,
            "error": None,
        }
