from __future__ import annotations

import json
from typing import Any, Dict

from .schema import parse_qwen_json, split_qwen_payload


QWEN_SECTION_SPECS: Dict[str, Dict[str, Any]] = {
    "grounding": {
        "required_keys": ["summary", "bbox_confidence", "mask_confidence", "multi_instance_note", "small_or_occluded"],
        "instruction": (
            "Infer logo grounding quality from the provided evidence. "
            "Judge whether the logo localization is likely reliable, small, occluded, or multi-instance."
        ),
        "schema_hint": {
            "summary": "short string",
            "bbox_confidence": "number or null",
            "mask_confidence": "number or null",
            "multi_instance_note": "string or null",
            "small_or_occluded": "boolean or null",
        },
    },
    "recognition": {
        "required_keys": ["logo_text", "brand", "parent_company", "sub_brand", "variant", "variant_reason", "confidence", "ambiguity"],
        "instruction": (
            "Infer which logo this is, which brand it belongs to, whether a sub-brand or product line is visible, "
            "and whether it looks like an old/new/icon-only/monochrome variant."
        ),
        "schema_hint": {
            "logo_text": "string or null",
            "brand": "string or null",
            "parent_company": "string or null",
            "sub_brand": "string or null",
            "variant": "string or null",
            "variant_reason": "string or null",
            "confidence": "number or null",
            "ambiguity": "string or null",
        },
    },
    "world_knowledge": {
        "required_keys": ["industry", "products_services", "target_market", "logo_era", "relationships", "scene_reasonableness", "scene_relation_type"],
        "instruction": (
            "Infer the brand's world knowledge and scene relationship. "
            "Explain likely industry, products/services, market, likely era/version, relationships, and why the logo appears in this scene."
        ),
        "schema_hint": {
            "industry": "string or null",
            "products_services": "array[string] or null",
            "target_market": "string or null",
            "logo_era": "string or null",
            "relationships": "array[string] or null",
            "scene_reasonableness": "string or null",
            "scene_relation_type": "string or null",
        },
    },
    "risk": {
        "required_keys": ["primary_or_background", "commercial_risk", "compliance_risk", "brand_exposure_type", "recommended_action", "replacement_impact", "risk_reason"],
        "instruction": (
            "Infer commercial/compliance/policy risk. "
            "Judge if the logo is a primary subject or background, whether it introduces ad/sponsor/IP risk, and what action is recommended."
        ),
        "schema_hint": {
            "primary_or_background": "string or null",
            "commercial_risk": "string or null",
            "compliance_risk": "string or null",
            "brand_exposure_type": "string or null",
            "recommended_action": "string or null",
            "replacement_impact": "string or null",
            "risk_reason": "string or null",
        },
    },
    "ambiguity": {
        "required_keys": ["needs_human_review", "uncertain_fields", "note"],
        "instruction": (
            "State whether a human reviewer is needed, which fields remain uncertain, and why."
        ),
        "schema_hint": {
            "needs_human_review": "boolean",
            "uncertain_fields": "array[string] or null",
            "note": "string or null",
        },
    },
}


def _normalize_section(section_name: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    spec = QWEN_SECTION_SPECS[section_name]
    normalized: Dict[str, Any] = {}
    for key in spec["required_keys"]:
        normalized[key] = parsed.get(key)
    if "_error" in parsed:
        normalized["_error"] = parsed.get("_error")
    return normalized


def build_qwen_prompt_payload(
    *,
    brand_hint: Any,
    category: Any,
    source_channel: Any,
    quality_status: Any,
    bbox_xyxy: Any,
    ocr_text: Any,
    clip_matches: Any,
    caption: Any,
    brand_record: Any = None,
    scene_bucket: Any = None,
) -> Dict[str, Any]:
    return {
        "brand_hint": brand_hint,
        "category": category,
        "source_channel": source_channel,
        "scene_bucket": scene_bucket,
        "quality_status": quality_status,
        "bbox_xyxy": bbox_xyxy,
        "ocr_text": ocr_text,
        "clip_matches": clip_matches,
        "caption": caption,
        "brand_record": brand_record,
    }


def build_qwen_text_only_payload(
    *,
    brand_hint: Any,
    category: Any,
    source_channel: Any,
    source_name: Any = None,
    scene_bucket: Any = None,
    quality_status: Any = None,
    product_name: Any = None,
    product_subtitle: Any = None,
    color_description: Any = None,
    image_url: Any = None,
    brand_record: Any = None,
) -> Dict[str, Any]:
    return {
        "mode": "text_only",
        "brand_hint": brand_hint,
        "category": category,
        "source_channel": source_channel,
        "source_name": source_name,
        "scene_bucket": scene_bucket,
        "quality_status": quality_status,
        "product_name": product_name,
        "product_subtitle": product_subtitle,
        "color_description": color_description,
        "image_url": image_url,
        "brand_record": brand_record,
        "bbox_xyxy": None,
        "ocr_text": None,
        "clip_matches": None,
        "caption": None,
    }


def run_qwen_logo_reasoning(qwen_engine: Any, prompt_payload: Dict[str, Any]) -> Dict[str, Any]:
    section_results: Dict[str, Any] = {}
    section_traces: Dict[str, Any] = {}

    base_system = (
        "You are a strict logo intelligence analyst. "
        "Return JSON only. No markdown. No prose outside JSON. "
        "If evidence is weak, use null and explain uncertainty in the provided fields."
    )

    context_text = json.dumps(prompt_payload, ensure_ascii=False)

    for section_name, spec in QWEN_SECTION_SPECS.items():
        prompt = (
            f"Task section: {section_name}\n"
            f"{spec['instruction']}\n"
            f"Return one JSON object with exactly these keys: {', '.join(spec['required_keys'])}.\n"
            f"Schema hint: {json.dumps(spec['schema_hint'], ensure_ascii=False)}\n"
            f"Context: {context_text}"
        )
        raw = qwen_engine.generate(prompt, system=base_system)
        parsed = parse_qwen_json(raw.get("text"))
        normalized = _normalize_section(section_name, parsed)
        section_results[section_name] = normalized
        section_traces[section_name] = {
            "prompt": prompt,
            "raw": raw,
            "parsed": parsed,
            "normalized": normalized,
        }

    full_payload = {
        "grounding": section_results.get("grounding"),
        "recognition": section_results.get("recognition"),
        "world_knowledge": section_results.get("world_knowledge"),
        "risk": section_results.get("risk"),
        "ambiguity": section_results.get("ambiguity"),
    }
    split_payload = split_qwen_payload(full_payload)
    return {
        "full_payload": full_payload,
        "split_payload": split_payload,
        "section_traces": section_traces,
    }
