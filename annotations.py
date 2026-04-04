from __future__ import annotations

import difflib
from typing import Any, Dict, Iterable, List

from .record_types import ProductRecord
from .schema import canonical_brand_id, image_external_key, json_text, logo_instance_id, utcnow_iso


def normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def metadata_ocr_signal(record: ProductRecord) -> Dict[str, Any]:
    brand = str(record.get("brand") or "").strip()
    fields = [
        str(record.get("logo_grounding_label") or ""),
        str(record.get("product_name") or ""),
        str(record.get("product_subtitle") or ""),
        str(record.get("color_description") or ""),
    ]
    haystack = " ".join(fields).lower()
    if brand and brand.lower() in haystack:
        return {
            "engine": "metadata_ocr",
            "text": brand,
            "confidence": 0.95,
            "matched_brand_name": brand,
        }
    if record.get("logo_grounding_label"):
        return {
            "engine": "metadata_ocr",
            "text": str(record.get("logo_grounding_label")),
            "confidence": 0.55,
            "matched_brand_name": None,
        }
    return {"engine": "metadata_ocr", "text": None, "confidence": 0.0, "matched_brand_name": None}


def similarity_brand_signal(record: ProductRecord, brand_name_index: Dict[str, str]) -> Dict[str, Any]:
    candidates = [
        str(record.get("brand") or ""),
        str(record.get("logo_grounding_label") or ""),
        str(record.get("product_name") or ""),
    ]
    best_ratio = 0.0
    best_brand_id = None
    best_brand_name = None
    for candidate in candidates:
        candidate_key = normalize_text(candidate)
        if not candidate_key:
            continue
        if candidate_key in brand_name_index:
            brand_id = brand_name_index[candidate_key]
            return {
                "engine": "brand_similarity",
                "brand_id": brand_id,
                "brand_name": candidate,
                "score": 0.98,
            }
        for alias, brand_id in brand_name_index.items():
            ratio = difflib.SequenceMatcher(a=candidate_key, b=alias).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_brand_id = brand_id
                best_brand_name = alias
    return {
        "engine": "brand_similarity",
        "brand_id": best_brand_id,
        "brand_name": best_brand_name,
        "score": round(best_ratio, 4),
    }


def ocr_brand_signal(ocr_payload: Dict[str, Any] | None, brand_name_index: Dict[str, str]) -> Dict[str, Any]:
    if not ocr_payload:
        return {"engine": "paddleocr", "text": None, "confidence": 0.0, "matched_brand_name": None, "matched_brand_id": None}
    text = str(ocr_payload.get("text") or "").strip()
    text_lower = text.lower()
    if not text_lower:
        return {
            "engine": str(ocr_payload.get("engine") or "paddleocr"),
            "text": None,
            "confidence": float(ocr_payload.get("confidence") or 0.0),
            "matched_brand_name": None,
            "matched_brand_id": None,
        }
    for alias, brand_id in brand_name_index.items():
        if alias and alias in text_lower:
            return {
                "engine": str(ocr_payload.get("engine") or "paddleocr"),
                "text": text,
                "confidence": float(ocr_payload.get("confidence") or 0.0),
                "matched_brand_name": alias,
                "matched_brand_id": brand_id,
            }
    return {
        "engine": str(ocr_payload.get("engine") or "paddleocr"),
        "text": text,
        "confidence": float(ocr_payload.get("confidence") or 0.0),
        "matched_brand_name": None,
        "matched_brand_id": None,
    }


def clip_brand_signal(clip_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    matches = list((clip_payload or {}).get("matches") or [])
    top_match = matches[0] if matches else None
    second_match = matches[1] if len(matches) > 1 else None
    return {
        "engine": str((clip_payload or {}).get("model_id") or "clip_brand_retrieval"),
        "brand_id": top_match.get("brand_id") if top_match else None,
        "brand_name": top_match.get("brand_name") if top_match else None,
        "score": float(top_match.get("score") or 0.0) if top_match else 0.0,
        "margin": (
            float(top_match.get("score") or 0.0) - float(second_match.get("score") or 0.0)
            if top_match and second_match
            else None
        ),
        "prompt": top_match.get("prompt") if top_match else None,
        "top_matches": matches,
    }


def caption_brand_signal(caption_payload: Dict[str, Any] | None, brand_name_index: Dict[str, str]) -> Dict[str, Any]:
    if not caption_payload:
        return {"engine": "caption", "brand_id": None, "brand_name": None, "score": 0.0, "text": None}
    texts = [
        str(caption_payload.get("full_image_caption") or "").strip(),
        str(caption_payload.get("logo_crop_caption") or "").strip(),
    ]
    joined = " ".join(texts).strip()
    joined_lower = joined.lower()
    if not joined_lower:
        return {
            "engine": str(caption_payload.get("model_id") or "caption"),
            "brand_id": None,
            "brand_name": None,
            "score": 0.0,
            "text": None,
        }
    for alias, brand_id in brand_name_index.items():
        if alias and alias in joined_lower:
            return {
                "engine": str(caption_payload.get("model_id") or "caption"),
                "brand_id": brand_id,
                "brand_name": alias,
                "score": 0.72,
                "text": joined,
            }
    return {
        "engine": str(caption_payload.get("model_id") or "caption"),
        "brand_id": None,
        "brand_name": None,
        "score": 0.0,
        "text": joined,
    }


def merge_signals(
    record: ProductRecord,
    brand_name_index: Dict[str, str],
    *,
    ocr_payload: Dict[str, Any] | None = None,
    clip_payload: Dict[str, Any] | None = None,
    caption_payload: Dict[str, Any] | None = None,
    use_clip_for_merge: bool = False,
) -> Dict[str, Any]:
    metadata_ocr = metadata_ocr_signal(record)
    ocr = ocr_brand_signal(ocr_payload, brand_name_index)
    clip = clip_brand_signal(clip_payload)
    caption = caption_brand_signal(caption_payload, brand_name_index)
    fallback = similarity_brand_signal(record, brand_name_index)

    attribution_source = "metadata_similarity"
    if ocr["matched_brand_id"]:
        merged_brand_id = ocr["matched_brand_id"]
        merged_brand_name = str(record.get("brand") or ocr["matched_brand_name"] or "")
        ambiguity_note = None
        confidence = max(float(record.get("logo_detection_score") or 0.0), float(ocr["confidence"] or 0.0))
        attribution_source = "ocr"
    elif use_clip_for_merge and clip["brand_id"] and clip["score"] >= 0.22:
        merged_brand_id = clip["brand_id"]
        merged_brand_name = str(clip["brand_name"] or record.get("brand") or "")
        ambiguity_note = None if (clip["margin"] is None or float(clip["margin"]) >= 0.02) else "ambiguous_clip_brand_retrieval"
        confidence = max(float(record.get("logo_detection_score") or 0.0), min(0.95, max(0.0, (float(clip["score"]) + 1.0) / 2.0)))
        attribution_source = "clip_retrieval"
    elif caption["brand_id"]:
        merged_brand_id = caption["brand_id"]
        merged_brand_name = str(record.get("brand") or caption["brand_name"] or "")
        ambiguity_note = "caption_brand_hint"
        confidence = max(float(record.get("logo_detection_score") or 0.0), float(caption["score"] or 0.0))
        attribution_source = "caption_hint"
    elif metadata_ocr["matched_brand_name"]:
        merged_brand_name = str(metadata_ocr["matched_brand_name"])
        merged_brand_id = brand_name_index.get(merged_brand_name.strip().lower(), canonical_brand_id(merged_brand_name))
        ambiguity_note = None
        confidence = max(float(record.get("logo_detection_score") or 0.0), float(metadata_ocr["confidence"]))
        attribution_source = "metadata_ocr"
    else:
        merged_brand_id = fallback["brand_id"] or canonical_brand_id(str(record.get("brand") or "unknown"))
        merged_brand_name = str(record.get("brand") or fallback.get("brand_name") or "")
        ambiguity_note = None if fallback["score"] >= 0.6 else "low_brand_similarity"
        confidence = max(float(record.get("logo_detection_score") or 0.0), float(fallback["score"] or 0.0))

    return {
        "ocr": ocr if ocr_payload is not None else metadata_ocr,
        "clip": clip,
        "caption": caption,
        "fallback": fallback,
        "clip_used_for_merge": use_clip_for_merge,
        "merged_brand_id": merged_brand_id,
        "merged_brand_name": merged_brand_name,
        "confidence": round(confidence, 4),
        "ambiguity_note": ambiguity_note,
        "attribution_source": attribution_source,
    }


def imported_logo_instances(
    segment_records: Iterable[Dict[str, Any]],
    image_id_by_external_key: Dict[str, str],
    brand_name_index: Dict[str, str],
    tier: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    timestamp = utcnow_iso()
    for record in segment_records:
        if record.get("logo_segmentation_status") != "ok":
            continue
        external_key = image_external_key(record)
        image_id = image_id_by_external_key.get(external_key)
        if not image_id:
            continue

        merged = merge_signals(record, brand_name_index)
        bbox = record.get("logo_bbox_xyxy") or record.get("logo_grounding_bbox_xyxy")
        detector_score = float(record.get("logo_detection_score") or record.get("logo_grounding_score") or 0.0)
        review_status = str(record.get("logo_bbox_review_status") or record.get("logo_mask_review_status") or "proposal")

        proposal = {
            "bbox_xyxy": bbox,
            "mask_path": record.get("logo_mask_path"),
            "brand": merged["merged_brand_name"],
            "grounding_label": record.get("logo_grounding_label"),
        }
        instance_id = logo_instance_id(image_id, proposal)

        rows.append(
            {
                "instance_id": instance_id,
                "image_id": image_id,
                "brand_id": merged["merged_brand_id"],
                "merged_brand_name": merged["merged_brand_name"],
                "detector_name": "imported_grounding_sam3",
                "ocr_engine": merged["ocr"]["engine"],
                "clip_engine": merged["clip"]["engine"],
                "bbox_json": json_text(bbox) if bbox else None,
                "polygon_json": None,
                "rotated_box_json": None,
                "mask_path": record.get("logo_mask_path"),
                "detector_score": detector_score,
                "ocr_text": merged["ocr"]["text"],
                "ocr_confidence": merged["ocr"]["confidence"],
                "clip_score": merged["clip"]["score"],
                "caption_text": merged.get("caption", {}).get("text"),
                "caption_model": merged.get("caption", {}).get("engine"),
                "attribution_json": json_text(
                    {
                        "source": merged.get("attribution_source"),
                        "clip": merged.get("clip"),
                        "caption": merged.get("caption"),
                        "fallback": merged.get("fallback"),
                    }
                ),
                "knowledge_json": None,
                "risk_json": None,
                "confidence": merged["confidence"],
                "ambiguity_note": merged["ambiguity_note"],
                "review_status": review_status,
                "tier": tier,
                "provenance_json": json_text(
                    {
                        "source": "imported_segment_records",
                        "logo_grounding_model_id": record.get("logo_grounding_model_id"),
                        "logo_prompt_context": record.get("logo_prompt_context"),
                        "logo_visualization_path": record.get("logo_visualization_path"),
                    }
                ),
                "raw_json": json_text(record),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    return rows
