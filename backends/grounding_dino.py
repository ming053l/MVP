from __future__ import annotations

from typing import Any, Dict, List

from PIL import Image
import torch

from .base import BackendMixin
from .common import AutoModelForZeroShotObjectDetection, AutoProcessor


class GroundingDINOProposalDetector(BackendMixin):
    def __init__(
        self,
        model_id: str = "IDEA-Research/grounding-dino-tiny",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        threshold: float = 0.25,
        text_threshold: float = 0.2,
        max_candidates: int = 5,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.device = device
        self.threshold = threshold
        self.text_threshold = text_threshold
        self.max_candidates = max_candidates
        self.processor = None
        self.model = None

        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def detect(self, image: Image.Image, prompts: List[str], expected_fraction_range: tuple[float, float]) -> List[Dict[str, Any]]:
        if self.processor is None or self.model is None:
            return []
        text = " ".join(f"{prompt}." for prompt in prompts)
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        results = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=self.threshold,
            text_threshold=self.text_threshold,
            target_sizes=[image.size[::-1]],
        )[0]

        width, height = image.size
        image_area = max(width * height, 1)
        low, high = expected_fraction_range
        candidates = []
        for box, score, label in zip(results["boxes"], results["scores"], results["text_labels"]):
            box_xyxy = [float(v) for v in box.tolist()]
            x0, y0, x1, y1 = box_xyxy
            area = max(0.0, (x1 - x0) * (y1 - y0))
            frac = area / image_area
            size_penalty = 0.0 if low <= frac <= high else 0.15
            rank_score = float(score) - size_penalty + (0.05 if "logo" in str(label).lower() else 0.0)
            candidates.append(
                {
                    "label": str(label),
                    "score": float(score),
                    "rank_score": rank_score,
                    "bbox_xyxy": box_xyxy,
                    "bbox_fraction": frac,
                    "detector_name": self.model_id,
                }
            )
        candidates.sort(key=lambda item: item["rank_score"], reverse=True)
        return candidates[: self.max_candidates]
