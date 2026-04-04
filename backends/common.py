from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoModelForZeroShotObjectDetection, AutoProcessor, AutoTokenizer, CLIPModel

from ..runtime import configure_runtime

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
    cache_path = Path(__file__).resolve().parent.parent.parent / "engine" / "model_cache" / "yolov8s-worldv2.pt"
    return str(cache_path)


def unwrap_clip_features(value: Any, embed_attr: str) -> torch.Tensor:
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
