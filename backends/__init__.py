from __future__ import annotations

from .base import BackendMixin, BackendProtocol
from .blip_caption import BLIPCaptionEngine
from .clip_brand import CLIPBrandRetriever
from .clip_logo import CLIPLogoQualityScorer
from .common import default_yoloworld_model_path
from .grounding_dino import GroundingDINOProposalDetector
from .llava_vlm import LLaMAVLMEngine
from .paddle_ocr import PaddleOCREngine
from .qwen_knowledge import QwenKnowledgeEngine
from .yolo_world import YOLOWorldLogoPrescreener

__all__ = [
    "BackendMixin",
    "BackendProtocol",
    "BLIPCaptionEngine",
    "CLIPBrandRetriever",
    "CLIPLogoQualityScorer",
    "GroundingDINOProposalDetector",
    "LLaMAVLMEngine",
    "PaddleOCREngine",
    "QwenKnowledgeEngine",
    "YOLOWorldLogoPrescreener",
    "default_yoloworld_model_path",
]
