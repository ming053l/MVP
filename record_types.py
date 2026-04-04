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


class BrandRow(TypedDict):
    brand_id: str
    canonical_name: str
    display_name: str
    tier: str
    industry: str | None
    country: str | None
    parent_company: str | None
    knowledge_json: str
    created_at: str
    updated_at: str


class ImageRow(TypedDict):
    image_id: str
    external_key: str
    brand_hint: str | None
    category: str | None
    source_name: str | None
    source_channel: str | None
    source_kind: str | None
    scene_bucket: str
    image_url: str | None
    local_image_path: str | None
    image_phash: str | None
    quality_status: str | None
    quality_score: float | None
    quality_gate_json: str | None
    difficulty_flags_json: str | None
    last_gated_at: str | None
    tier: str
    capture_context_json: str
    raw_json: str
    created_at: str
    updated_at: str


class LogoInstanceRow(TypedDict):
    instance_id: str
    image_id: str
    brand_id: str | None
    merged_brand_name: str | None
    detector_name: str | None
    ocr_engine: str | None
    clip_engine: str | None
    bbox_json: str | None
    polygon_json: str | None
    rotated_box_json: str | None
    mask_path: str | None
    detector_score: float | None
    ocr_text: str | None
    ocr_confidence: float | None
    clip_score: float | None
    caption_text: str | None
    caption_model: str | None
    attribution_json: str | None
    knowledge_json: str | None
    risk_json: str | None
    confidence: float | None
    ambiguity_note: str | None
    review_status: str | None
    tier: str
    provenance_json: str
    raw_json: str
    created_at: str
    updated_at: str
