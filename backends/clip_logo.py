from __future__ import annotations

from typing import Any, Dict

from PIL import Image
import torch
import torch.nn.functional as F

from .base import BackendMixin
from .common import AutoProcessor, CLIPModel, unwrap_clip_features


class CLIPLogoQualityScorer(BackendMixin):
    def __init__(
        self,
        model_id: str = "openai/clip-vit-base-patch32",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.device = device
        self.processor = None
        self.model = None
        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = CLIPModel.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def score(self, image: Image.Image, prompt: str = "a photo with a brand logo") -> Dict[str, Any]:
        if self.processor is None or self.model is None:
            return {"model_id": self.model_id, "score": None, "error": self.error}
        inputs = self.processor(images=image, text=[prompt], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            image_features = unwrap_clip_features(
                self.model.get_image_features(pixel_values=inputs["pixel_values"]),
                "image_embeds",
            )
            text_features = unwrap_clip_features(
                self.model.get_text_features(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                ),
                "text_embeds",
            )
            image_features = F.normalize(image_features.float(), dim=-1)
            text_features = F.normalize(text_features.float(), dim=-1)
            score = float((image_features @ text_features.T).squeeze().item())
        return {"model_id": self.model_id, "score": score, "error": None}
