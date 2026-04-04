from __future__ import annotations

from typing import Any, Dict

from PIL import Image
import torch

from .base import BackendMixin
from .common import AutoModelForVision2Seq, AutoProcessor, LlavaForConditionalGeneration, LlavaProcessor


class LLaMAVLMEngine(BackendMixin):
    def __init__(
        self,
        model_id: str = "llava-hf/llava-1.5-7b-hf",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 64,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.processor = None
        self.model = None

        try:
            model_id_lower = model_id.lower()
            if "llava" in model_id_lower and LlavaProcessor is not None and LlavaForConditionalGeneration is not None:
                self.processor = LlavaProcessor.from_pretrained(model_id)
                self.model = LlavaForConditionalGeneration.from_pretrained(model_id).to(device)
            elif AutoModelForVision2Seq is not None:
                self.processor = AutoProcessor.from_pretrained(model_id)
                self.model = AutoModelForVision2Seq.from_pretrained(model_id).to(device)
            else:
                self.error = "Vision2Seq backend is not available in transformers"
                return
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def caption(self, image: Image.Image, prompt: str | None = None) -> Dict[str, Any]:
        if self.processor is None or self.model is None:
            return {"model_id": self.model_id, "text": None, "error": self.error}
        if prompt is None:
            prompt = "Describe the brand, object, and photo scene."
        text_prompt = prompt
        if hasattr(self.processor, "apply_chat_template"):
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            try:
                text_prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
            except Exception:
                text_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
        elif "llava" in self.model_id.lower():
            text_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
        inputs = self.processor(images=image, text=text_prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        return {"model_id": self.model_id, "text": text or None, "prompt": prompt, "error": None}
