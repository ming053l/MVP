from __future__ import annotations

from typing import Any, Dict, Iterable, List

from PIL import Image
import torch
import torch.nn.functional as F

from .base import BackendMixin
from .common import AutoProcessor, CLIPModel, unwrap_clip_features


class CLIPBrandRetriever(BackendMixin):
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

    def _brand_texts(self, brand_catalog: Iterable[Dict[str, Any]], object_hint: str | None = None) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        suffix = f" on a {object_hint}" if object_hint else ""
        templates = [
            "{brand} logo",
            "a photo of the {brand} logo",
            "a product photo showing the {brand} logo",
            "a brand logo for {brand}",
            "a product from {brand}" + suffix,
        ]
        for brand in brand_catalog:
            brand_id = str(brand.get("brand_id") or "").strip()
            display_name = str(brand.get("display_name") or brand.get("canonical_name") or "").strip()
            if not brand_id or not display_name:
                continue
            alias_values = [display_name]
            for alias in brand.get("aliases_en") or []:
                alias_text = str(alias).strip()
                if alias_text:
                    alias_values.append(alias_text)
            seen_aliases = set()
            for alias in alias_values:
                alias_key = alias.lower()
                if alias_key in seen_aliases:
                    continue
                seen_aliases.add(alias_key)
                for template in templates:
                    entries.append(
                        {
                            "brand_id": brand_id,
                            "brand_name": display_name,
                            "prompt": template.format(brand=alias),
                        }
                    )
        return entries

    def retrieve(
        self,
        image: Image.Image,
        brand_catalog: Iterable[Dict[str, Any]],
        *,
        object_hint: str | None = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        if self.processor is None or self.model is None:
            return {"model_id": self.model_id, "matches": [], "error": self.error}

        entries = self._brand_texts(brand_catalog, object_hint=object_hint)
        if not entries:
            return {"model_id": self.model_id, "matches": [], "error": "empty_brand_catalog"}

        prompts = [entry["prompt"] for entry in entries]
        image_inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        text_inputs = self.processor(text=prompts, return_tensors="pt", padding=True, truncation=True).to(self.device)

        with torch.no_grad():
            image_features = unwrap_clip_features(
                self.model.get_image_features(pixel_values=image_inputs["pixel_values"]),
                "image_embeds",
            )
            text_features = unwrap_clip_features(
                self.model.get_text_features(
                    input_ids=text_inputs["input_ids"],
                    attention_mask=text_inputs.get("attention_mask"),
                ),
                "text_embeds",
            )
            image_features = F.normalize(image_features.float(), dim=-1)
            text_features = F.normalize(text_features.float(), dim=-1)
            scores = (image_features @ text_features.T).squeeze(0).tolist()

        best_by_brand: Dict[str, Dict[str, Any]] = {}
        for entry, score in zip(entries, scores):
            brand_id = entry["brand_id"]
            current = best_by_brand.get(brand_id)
            if current is None or float(score) > float(current["score"]):
                best_by_brand[brand_id] = {
                    "brand_id": brand_id,
                    "brand_name": entry["brand_name"],
                    "score": float(score),
                    "prompt": entry["prompt"],
                }

        matches = sorted(best_by_brand.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        return {"model_id": self.model_id, "matches": matches, "error": None}
