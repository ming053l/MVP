from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import jsonschema
except Exception:  # pragma: no cover - optional runtime dependency
    jsonschema = None


TIER_VALUES = ("proposal", "silver", "gold")
QWEN_REQUIRED_KEYS = ("grounding", "recognition", "world_knowledge", "risk", "ambiguity")


def _load_schema_file(name: str) -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / name
    return json.loads(path.read_text(encoding="utf-8"))


QWEN_LOGO_INTELLIGENCE_SCHEMA = _load_schema_file("qwen_logo_intelligence.schema.json")
QWEN_KNOWLEDGE_SCHEMA = _load_schema_file("qwen_knowledge.schema.json")
QWEN_RISK_SCHEMA = _load_schema_file("qwen_risk.schema.json")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    return cleaned.strip("-") or "unknown"


def stable_hash(payload: object, length: int = 16) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:length]


def canonical_brand_id(name: str) -> str:
    return slugify(name)


def image_external_key(record: Dict[str, Any]) -> str:
    source_payload = {
        "record_id": record.get("record_id"),
        "brand": record.get("brand"),
        "category": record.get("category"),
        "product_name": record.get("product_name"),
        "model_code": record.get("model_code"),
        "product_url": record.get("product_url"),
        "image_url": record.get("image_url"),
        "local_image_path": record.get("local_image_path"),
        "source_channel": record.get("source_channel"),
    }
    return str(record.get("record_id") or stable_hash(source_payload))


def image_id_from_record(record: Dict[str, Any]) -> str:
    return stable_hash(
        {
            "external_key": image_external_key(record),
            "brand": record.get("brand"),
            "category": record.get("category"),
        }
    )


def logo_instance_id(image_id: str, proposal: Dict[str, Any]) -> str:
    return stable_hash(
        {
            "image_id": image_id,
            "bbox": proposal.get("bbox_xyxy") or proposal.get("logo_bbox_xyxy"),
            "mask_path": proposal.get("mask_path") or proposal.get("logo_mask_path"),
            "brand": proposal.get("merged_brand_name") or proposal.get("brand"),
            "label": proposal.get("grounding_label") or proposal.get("logo_grounding_label"),
        }
    )


@dataclass(frozen=True)
class BrandRecordRow:
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


@dataclass(frozen=True)
class ImageRecordRow:
    image_id: str
    external_key: str
    brand_hint: str | None
    category: str | None
    source_name: str | None
    source_channel: str | None
    source_kind: str | None
    scene_bucket: str | None
    image_url: str | None
    local_image_path: str | None
    image_phash: str | None
    tier: str
    capture_context_json: str
    raw_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LogoInstanceRow:
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


def scene_bucket_from_record(record: Dict[str, Any]) -> str:
    capture_context = record.get("capture_context") or {}
    source_channel = str(record.get("source_channel") or "").strip().lower()
    scene_type = str(capture_context.get("scene_type") or "").strip().lower()
    if scene_type:
        return scene_type
    if source_channel:
        return source_channel
    return str(record.get("category") or "unknown").strip().lower()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def resolve_local_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value))


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def parse_qwen_json(text: str | None) -> Dict[str, Any]:
    if not text:
        return {"_error": "empty_response"}
    block = _extract_json_block(text)
    if not block:
        return {"_error": "no_json_block", "_raw": text}
    try:
        return json.loads(block)
    except json.JSONDecodeError as exc:
        return {"_error": f"json_decode_error: {exc}", "_raw": text}


def validate_qwen_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    for key in QWEN_REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"missing:{key}")
    if jsonschema is not None and not errors:
        try:
            jsonschema.validate(instance=payload, schema=QWEN_LOGO_INTELLIGENCE_SCHEMA)
        except Exception as exc:
            errors.append(f"jsonschema:{exc}")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def split_qwen_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload:
        return {
            "knowledge_json": {"_error": "empty_payload"},
            "risk_json": {"_error": "empty_payload"},
            "validation": {"valid": False, "errors": ["empty_payload"]},
        }
    validation = validate_qwen_payload(payload)
    knowledge = {
        "grounding": payload.get("grounding"),
        "recognition": payload.get("recognition"),
        "world_knowledge": payload.get("world_knowledge"),
        "ambiguity": payload.get("ambiguity"),
    }
    risk = {"risk": payload.get("risk")}
    if jsonschema is not None:
        try:
            jsonschema.validate(instance=knowledge, schema=QWEN_KNOWLEDGE_SCHEMA)
        except Exception as exc:
            validation["valid"] = False
            validation["errors"].append(f"knowledge_schema:{exc}")
        try:
            jsonschema.validate(instance=risk, schema=QWEN_RISK_SCHEMA)
        except Exception as exc:
            validation["valid"] = False
            validation["errors"].append(f"risk_schema:{exc}")
    return {
        "knowledge_json": knowledge,
        "risk_json": risk,
        "validation": validation,
    }
