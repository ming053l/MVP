from __future__ import annotations

from typing import Any, Dict

import torch

from .base import BackendMixin
from .common import AutoModelForCausalLM, AutoTokenizer


class QwenKnowledgeEngine(BackendMixin):
    def __init__(
        self,
        model_id: str = "Qwen/Qwen2.5-7B-Instruct",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 512,
        temperature: float = 0.2,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.tokenizer = None
        self.model = None
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
            self.model = AutoModelForCausalLM.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = self.format_exception(exc)

    @property
    def available(self) -> bool:
        return self.tokenizer is not None and self.model is not None

    def generate(self, prompt: str, system: str | None = None) -> Dict[str, Any]:
        if self.tokenizer is None or self.model is None:
            return {"model_id": self.model_id, "text": None, "error": self.error, "prompt": prompt}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        if hasattr(self.tokenizer, "apply_chat_template"):
            text_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text_prompt = (system + "\n" if system else "") + prompt
        inputs = self.tokenizer(text_prompt, return_tensors="pt").to(self.device)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=self.temperature,
            )
        generated_ids = generated[0][prompt_tokens:]
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        if not text.strip():
            text = self.tokenizer.decode(generated[0], skip_special_tokens=True)
        return {"model_id": self.model_id, "text": text.strip() or None, "error": None, "prompt": prompt}
