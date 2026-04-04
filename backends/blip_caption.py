from __future__ import annotations

from typing import Any, Dict

from PIL import Image
import torch

from .base import BackendMixin
from .common import BlipForConditionalGeneration, BlipProcessor


class BLIPCaptionEngine(BackendMixin):
    def __init__(
        self,
        model_id: str = "Salesforce/blip-image-captioning-base",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 40,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.processor = None
        self.model = None
        if BlipProcessor is None or BlipForConditionalGeneration is None:
            self.error = "BLIP captioning dependencies are not available"
            return
        try:
            self.processor = BlipProcessor.from_pretrained(model_id)
            self.model = BlipForConditionalGeneration.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def caption(self, image: Image.Image, prompt: str | None = None) -> Dict[str, Any]:
        if self.processor is None or self.model is None:
            return {"model_id": self.model_id, "text": None, "error": self.error}

        kwargs: Dict[str, Any] = {"images": image, "return_tensors": "pt"}
        if prompt:
            kwargs["text"] = prompt
        inputs = self.processor(**kwargs).to(self.device)
        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        return {"model_id": self.model_id, "text": text or None, "prompt": prompt, "error": None}
