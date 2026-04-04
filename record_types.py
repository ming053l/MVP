from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class ProductRecord(TypedDict, total=False):
    brand: str
    category: str
    source: str
    source_channel: str
    source_kind: str
    image_url: str
    local_image_path: str
    scene_bucket: str
    capture_context: Dict[str, Any]
    product_name: str
    product_subtitle: str
    color_description: str
    logo_grounding_label: str
    logo_detection_score: float
    logo_grounding_score: float
    logo_bbox_xyxy: List[float]
    logo_grounding_bbox_xyxy: List[float]
    logo_mask_path: str
    logo_bbox_review_status: str
    logo_mask_review_status: str
    logo_visualization_path: str
    logo_prompt_context: Dict[str, Any]
    logo_segmentation_status: str
    logo_grounding_model_id: str


class BrandKnowledgeRecord(TypedDict, total=False):
    brand_id: str
    canonical_name: str
    display_name: str
    label: str
    query: str
    aliases_en: List[str]
    industries: List[str]
    countries: List[str]
    parent_organizations: List[str]
    matched: bool


class BrandCatalogEntry(TypedDict, total=False):
    brand_id: str
    canonical_name: str
    display_name: str
    aliases_en: List[str]


class OCRPayload(TypedDict, total=False):
    engine: str
    text: str | None
    confidence: float
    lines: List[Dict[str, Any]]
    error: str | None


class DetectionPayload(TypedDict, total=False):
    bbox_xyxy: List[float]
    detector_name: str
    detector_score: float
    detector_label: str
    prompt_context: Dict[str, Any]
    prompt_variants: List[str]
    ocr: OCRPayload
