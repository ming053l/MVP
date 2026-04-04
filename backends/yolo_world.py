from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from .base import BackendMixin
from .common import YOLOWorld, default_yoloworld_model_path


class YOLOWorldLogoPrescreener(BackendMixin):
    def __init__(
        self,
        model_id: str = default_yoloworld_model_path(),
        labels: Optional[List[str]] = None,
        conf_threshold: float = 0.3,
        device: str = "cpu",
        max_candidates: int = 5,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.labels = labels or ["logo", "brand logo", "company logo"]
        self.conf_threshold = conf_threshold
        self.device = device
        self.max_candidates = max_candidates
        self.model = None
        if YOLOWorld is None:
            self.error = "ultralytics is not installed"
            return
        try:
            model_path = Path(self.model_id)
            if model_path.suffix == ".pt":
                model_path.parent.mkdir(parents=True, exist_ok=True)
            load_target = str(model_path) if model_path.exists() else model_id
            self.model = YOLOWorld(load_target)
            self.model.set_classes(self.labels)
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.model is not None

    def detect(self, image: Image.Image) -> Dict[str, Any]:
        if self.model is None:
            return {"model_id": self.model_id, "detections": [], "error": self.error}
        results = self.model.predict(
            source=np.asarray(image),
            conf=self.conf_threshold,
            verbose=False,
            device=self.device,
            max_det=self.max_candidates,
        )
        detections: List[Dict[str, Any]] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().tolist()
            confs = boxes.conf.cpu().tolist()
            classes = boxes.cls.cpu().tolist()
            for bbox, conf, cls_idx in zip(xyxy, confs, classes):
                label = names.get(int(cls_idx), str(cls_idx)) if isinstance(names, dict) else str(cls_idx)
                detections.append(
                    {
                        "bbox_xyxy": [float(v) for v in bbox],
                        "score": float(conf),
                        "label": str(label),
                    }
                )
        detections.sort(key=lambda item: item["score"], reverse=True)
        return {"model_id": self.model_id, "detections": detections[: self.max_candidates], "error": None}
