from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, AutoTokenizer, AutoModelForCausalLM, CLIPModel

from .runtime import configure_runtime

configure_runtime()


try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover - optional runtime dependency
    PaddleOCR = None  # type: ignore[assignment]

try:
    from ultralytics import YOLOWorld
except Exception:  # pragma: no cover - optional runtime dependency
    YOLOWorld = None  # type: ignore[assignment]

try:
    from transformers import BlipForConditionalGeneration, BlipProcessor
except Exception:  # pragma: no cover - optional runtime dependency
    BlipForConditionalGeneration = None  # type: ignore[assignment]
    BlipProcessor = None  # type: ignore[assignment]

try:
    from transformers import AutoModelForVision2Seq
except Exception:  # pragma: no cover - optional runtime dependency
    AutoModelForVision2Seq = None  # type: ignore[assignment]

try:
    from transformers import LlavaForConditionalGeneration, LlavaProcessor
except Exception:  # pragma: no cover - optional runtime dependency
    LlavaForConditionalGeneration = None  # type: ignore[assignment]
    LlavaProcessor = None  # type: ignore[assignment]


def default_yoloworld_model_path() -> str:
    cache_path = Path(__file__).resolve().parent.parent / "engine" / "model_cache" / "yolov8s-worldv2.pt"
    return str(cache_path)


class PaddleOCREngine:
    def __init__(self, lang: str = "en") -> None:
        configure_runtime()
        self.lang = lang
        self.error: Optional[str] = None
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
            self.error = f"{type(exc).__name__}: {exc}"

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


class GroundingDINOProposalDetector:
    def __init__(
        self,
        model_id: str = "IDEA-Research/grounding-dino-tiny",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        threshold: float = 0.25,
        text_threshold: float = 0.2,
        max_candidates: int = 5,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.threshold = threshold
        self.text_threshold = text_threshold
        self.max_candidates = max_candidates
        self.error: Optional[str] = None
        self.processor = None
        self.model = None

        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = f"{type(exc).__name__}: {exc}"

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


class CLIPLogoQualityScorer:
    def __init__(
        self,
        model_id: str = "openai/clip-vit-base-patch32",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.error: Optional[str] = None
        self.processor = None
        self.model = None
        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = CLIPModel.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def _unwrap_features(self, value: Any, embed_attr: str) -> torch.Tensor:
        if isinstance(value, torch.Tensor):
            return value
        if hasattr(value, embed_attr):
            tensor = getattr(value, embed_attr)
            if isinstance(tensor, torch.Tensor):
                return tensor
        if hasattr(value, "pooler_output"):
            tensor = getattr(value, "pooler_output")
            if isinstance(tensor, torch.Tensor):
                return tensor
        raise TypeError(f"Unsupported CLIP feature output: {type(value).__name__}")

    def score(self, image: Image.Image, prompt: str = "a photo with a brand logo") -> Dict[str, Any]:
        if self.processor is None or self.model is None:
            return {"model_id": self.model_id, "score": None, "error": self.error}
        inputs = self.processor(images=image, text=[prompt], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            image_features = self._unwrap_features(
                self.model.get_image_features(pixel_values=inputs["pixel_values"]),
                "image_embeds",
            )
            text_features = self._unwrap_features(
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


class CLIPBrandRetriever:
    def __init__(
        self,
        model_id: str = "openai/clip-vit-base-patch32",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.error: Optional[str] = None
        self.processor = None
        self.model = None
        try:
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = CLIPModel.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return self.processor is not None and self.model is not None

    def _unwrap_features(self, value: Any, embed_attr: str) -> torch.Tensor:
        if isinstance(value, torch.Tensor):
            return value
        if hasattr(value, embed_attr):
            tensor = getattr(value, embed_attr)
            if isinstance(tensor, torch.Tensor):
                return tensor
        if hasattr(value, "pooler_output"):
            tensor = getattr(value, "pooler_output")
            if isinstance(tensor, torch.Tensor):
                return tensor
        raise TypeError(f"Unsupported CLIP feature output: {type(value).__name__}")

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
            image_features = self._unwrap_features(
                self.model.get_image_features(pixel_values=image_inputs["pixel_values"]),
                "image_embeds",
            )
            text_features = self._unwrap_features(
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


class BLIPCaptionEngine:
    def __init__(
        self,
        model_id: str = "Salesforce/blip-image-captioning-base",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 40,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.error: Optional[str] = None
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
            self.error = f"{type(exc).__name__}: {exc}"

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


class LLaMAVLMEngine:
    def __init__(
        self,
        model_id: str = "llava-hf/llava-1.5-7b-hf",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 64,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.error: Optional[str] = None
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
            self.error = f"{type(exc).__name__}: {exc}"

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


class QwenKnowledgeEngine:
    def __init__(
        self,
        model_id: str = "Qwen/Qwen2.5-7B-Instruct",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        max_new_tokens: int = 512,
        temperature: float = 0.2,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.error: Optional[str] = None
        self.tokenizer = None
        self.model = None
        try:
            if AutoTokenizer is None or AutoModelForCausalLM is None:
                self.error = "Text-generation backend is not available in transformers"
                return
            self.tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
            self.model = AutoModelForCausalLM.from_pretrained(model_id).to(device)
            self.model.eval()
        except Exception as exc:  # pragma: no cover - runtime dependency
            self.error = f"{type(exc).__name__}: {exc}"

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
        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=self.temperature,
            )
        text = self.tokenizer.decode(generated[0], skip_special_tokens=True)
        return {"model_id": self.model_id, "text": text.strip() or None, "error": None, "prompt": prompt}


class YOLOWorldLogoPrescreener:
    def __init__(
        self,
        model_id: str = default_yoloworld_model_path(),
        labels: Optional[List[str]] = None,
        conf_threshold: float = 0.3,
        device: str = "cpu",
        max_candidates: int = 5,
    ) -> None:
        self.model_id = model_id
        self.labels = labels or ["logo", "brand logo", "company logo"]
        self.conf_threshold = conf_threshold
        self.device = device
        self.max_candidates = max_candidates
        self.error: Optional[str] = None
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
            self.error = f"{type(exc).__name__}: {exc}"

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
