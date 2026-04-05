from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from .annotations import merge_signals
from .backends import BLIPCaptionEngine, CLIPBrandRetriever, GroundingDINOProposalDetector, LLaMAVLMEngine, PaddleOCREngine, QwenKnowledgeEngine
from .db import EngineDB
from .qwen_reasoning import build_qwen_prompt_payload, build_qwen_text_only_payload, run_qwen_logo_reasoning
from .record_types import BrandCatalogEntry, BrandKnowledgeRecord, DetectionPayload, LogoInstanceRow, OCRPayload, ProductRecord
from .schema import canonical_brand_id, json_text, logo_instance_id, utcnow_iso
from .verifier import classify_review_bucket, verify_text_consistency


def brand_context_from_db(db: EngineDB) -> Dict[str, BrandKnowledgeRecord]:
    rows = db.conn.execute("SELECT canonical_name, display_name, knowledge_json FROM brand_records").fetchall()
    context: Dict[str, BrandKnowledgeRecord] = {}
    for row in rows:
        payload = json.loads(str(row["knowledge_json"]))
        for key in (row["canonical_name"], row["display_name"], payload.get("query"), payload.get("label")):
            if key:
                context[str(key).strip().lower()] = payload
        for alias in payload.get("aliases_en") or []:
            if alias:
                context[str(alias).strip().lower()] = payload
    return context


def brand_catalog_from_db(db: EngineDB) -> List[BrandCatalogEntry]:
    rows = db.conn.execute("SELECT brand_id, canonical_name, display_name, knowledge_json FROM brand_records ORDER BY display_name").fetchall()
    catalog: List[BrandCatalogEntry] = []
    for row in rows:
        payload = json.loads(str(row["knowledge_json"]))
        catalog.append(
            {
                "brand_id": str(row["brand_id"]),
                "canonical_name": str(row["canonical_name"]),
                "display_name": str(row["display_name"]),
                "aliases_en": payload.get("aliases_en") or [],
            }
        )
    return catalog


def crop_bbox(image: Image.Image, bbox_xyxy: List[float]) -> Image.Image:
    x0, y0, x1, y1 = [int(round(v)) for v in bbox_xyxy]
    left = max(0, min(image.width, x0))
    upper = max(0, min(image.height, y0))
    right = max(left + 1, min(image.width, x1))
    lower = max(upper + 1, min(image.height, y1))
    return image.crop((left, upper, right, lower))


def detect_and_ocr_image(
    image_path: str | Path,
    record: ProductRecord,
    brand_context: Optional[BrandKnowledgeRecord],
    detector: GroundingDINOProposalDetector,
    ocr_engine: PaddleOCREngine | None,
    skip_ocr: bool = False,
) -> Optional[DetectionPayload]:
    from logo_segmentation_pipeline import build_prompts

    with Image.open(image_path) as image:
        image = image.convert("RGB")
        prompts, prompt_context = build_prompts(record, brand_context)
        candidates = detector.detect(image, prompts, prompt_context["expected_logo_fraction_range"])
        if not candidates:
            return None
        best = candidates[0]
    if skip_ocr or ocr_engine is None:
        ocr_result: OCRPayload = {
            "engine": "paddleocr",
            "text": None,
            "confidence": 0.0,
            "lines": [],
            "error": "disabled",
        }
    else:
        ocr_result = ocr_engine.recognize(image_path, crop_box_xyxy=best["bbox_xyxy"])
    return {
        "bbox_xyxy": best["bbox_xyxy"],
        "detector_name": best["detector_name"],
        "detector_score": best["score"],
        "detector_label": best["label"],
        "prompt_context": prompt_context,
        "prompt_variants": prompts,
        "ocr": ocr_result,
    }


def text_only_detection(record: ProductRecord) -> DetectionPayload:
    return {
        "bbox_xyxy": [],
        "detector_name": "text_only_metadata",
        "detector_score": 0.0,
        "detector_label": str(record.get("brand") or record.get("category") or "text_only"),
        "prompt_context": {"mode": "text_only"},
        "prompt_variants": [],
        "ocr": {
            "engine": "text_only",
            "text": str(record.get("brand") or record.get("logo_grounding_label") or "").strip() or None,
            "confidence": 0.0,
            "lines": [],
            "error": "text_only_mode",
        },
    }


def annotate_db_proposals(
    db: EngineDB,
    *,
    limit: Optional[int] = None,
    source_channel: Optional[str] = None,
    tier: str = "proposal",
    dry_run: bool = False,
    resume: bool = False,
    allow_filtered: bool = False,
    detector_model_id: str = "IDEA-Research/grounding-dino-tiny",
    clip_retrieval_model_id: str = "openai/clip-vit-base-patch32",
    caption_model_id: str = "Salesforce/blip-image-captioning-base",
    skip_detector: bool = False,
    skip_ocr: bool = False,
    skip_clip_retrieval: bool = False,
    skip_captioning: bool = False,
    vlm_model_id: str = "llava-hf/llava-1.5-7b-hf",
    use_vlm: bool = False,
    use_qwen_qa: bool = False,
    qwen_model_id: str = "Qwen/Qwen2.5-7B-Instruct",
) -> Dict[str, Any]:
    detector = None if skip_detector else GroundingDINOProposalDetector(model_id=detector_model_id)
    ocr_engine = None if skip_ocr else PaddleOCREngine(lang="en")
    clip_retriever = None if skip_clip_retrieval else CLIPBrandRetriever(model_id=clip_retrieval_model_id)
    captioner = None if skip_captioning else BLIPCaptionEngine(model_id=caption_model_id)
    vlm_engine = LLaMAVLMEngine(model_id=vlm_model_id) if use_vlm else None
    qwen_engine = QwenKnowledgeEngine(model_id=qwen_model_id) if use_qwen_qa else None
    brand_index = db.brand_name_index()
    known_brand_ids = db.brand_ids()
    brand_context_index = brand_context_from_db(db)
    brand_catalog = brand_catalog_from_db(db)
    existing_instance_ids = db.existing_instance_ids()

    query = "SELECT image_id, raw_json, local_image_path, brand_hint, source_channel, quality_status FROM image_records"
    conditions = []
    params: List[Any] = []
    if source_channel:
        conditions.append("source_channel = ?")
        params.append(source_channel)
    if not allow_filtered:
        conditions.append("(quality_status IS NULL OR quality_status = 'passed')")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at, image_id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    image_rows = db.conn.execute(query, params).fetchall()
    rows: List[LogoInstanceRow] = []
    skipped_existing = 0
    detector_failures = 0
    text_only_instances = 0
    verification_conflicts = 0
    review_bucket_counts = {"auto_accept": 0, "spot_check": 0, "must_review": 0}
    for row in image_rows:
        record: ProductRecord = json.loads(str(row["raw_json"]))
        image_path = row["local_image_path"]
        brand_key = str(record.get("brand") or row["brand_hint"] or "").strip().lower()
        detection: DetectionPayload | None = None
        image_exists = bool(image_path and Path(str(image_path)).exists())
        if detector is not None and detector.available and image_exists:
            detection = detect_and_ocr_image(
                image_path=image_path,
                record=record,
                brand_context=brand_context_index.get(brand_key),
                detector=detector,
                ocr_engine=ocr_engine,
                skip_ocr=skip_ocr,
            )
            if not detection:
                detector_failures += 1
        else:
            detector_failures += 1

        if detection is None:
            detection = text_only_detection(record)
            text_only_instances += 1

        ocr_payload = dict(detection["ocr"])
        clip_payload = None
        caption_payload = None
        vlm_payload = None
        qwen_payload = None
        if (
            (clip_retriever is not None and clip_retriever.available)
            or (captioner is not None and captioner.available)
            or (vlm_engine is not None and vlm_engine.available)
        ) and image_exists and detection["detector_name"] != "text_only_metadata" and detection["bbox_xyxy"]:
            with Image.open(str(image_path)) as opened:
                image = opened.convert("RGB")
                logo_crop = crop_bbox(image, detection["bbox_xyxy"])
                if clip_retriever is not None and clip_retriever.available:
                    clip_payload = clip_retriever.retrieve(
                        logo_crop,
                        brand_catalog,
                        object_hint=str(record.get("category") or "").strip().lower() or None,
                    )
                if vlm_engine is not None and vlm_engine.available and str(row["quality_status"] or "") == "passed":
                    full_caption = vlm_engine.caption(image, prompt="Describe the brand, object, and photo scene.")
                    crop_caption = vlm_engine.caption(logo_crop, prompt="Describe the logo, brand, and object in this crop.")
                    vlm_payload = {
                        "model_id": vlm_engine.model_id,
                        "full_image_caption": full_caption.get("text"),
                        "logo_crop_caption": crop_caption.get("text"),
                        "full_image_prompt": full_caption.get("prompt"),
                        "logo_crop_prompt": crop_caption.get("prompt"),
                        "full_image_error": full_caption.get("error"),
                        "logo_crop_error": crop_caption.get("error"),
                    }
                if captioner is not None and captioner.available and str(row["quality_status"] or "") == "passed":
                    full_caption = captioner.caption(image, prompt="Describe the brand, object, and photo scene.")
                    crop_caption = captioner.caption(logo_crop, prompt="Describe the logo, brand, and object in this crop.")
                    caption_payload = {
                        "model_id": captioner.model_id,
                        "full_image_caption": full_caption.get("text"),
                        "logo_crop_caption": crop_caption.get("text"),
                        "full_image_prompt": full_caption.get("prompt"),
                        "logo_crop_prompt": crop_caption.get("prompt"),
                        "full_image_error": full_caption.get("error"),
                        "logo_crop_error": crop_caption.get("error"),
                    }

        qwen_structured = None
        if qwen_engine is not None and qwen_engine.available and (str(row["quality_status"] or "") == "passed" or detection["detector_name"] == "text_only_metadata"):
            if detection["detector_name"] == "text_only_metadata":
                prompt_payload = build_qwen_text_only_payload(
                    brand_hint=record.get("brand"),
                    category=record.get("category"),
                    source_channel=record.get("source_channel"),
                    source_name=record.get("source"),
                    scene_bucket=record.get("scene_bucket"),
                    quality_status=row["quality_status"],
                    product_name=record.get("product_name"),
                    product_subtitle=record.get("product_subtitle"),
                    color_description=record.get("color_description"),
                    image_url=record.get("image_url"),
                    brand_record=brand_context_index.get(brand_key),
                )
            else:
                prompt_payload = build_qwen_prompt_payload(
                    brand_hint=record.get("brand"),
                    category=record.get("category"),
                    source_channel=record.get("source_channel"),
                    scene_bucket=record.get("scene_bucket"),
                    quality_status=row["quality_status"],
                    bbox_xyxy=detection.get("bbox_xyxy"),
                    ocr_text=ocr_payload.get("text"),
                    clip_matches=(clip_payload or {}).get("matches") if clip_payload else None,
                    caption=(vlm_payload or caption_payload or {}).get("logo_crop_caption")
                    or (vlm_payload or caption_payload or {}).get("full_image_caption"),
                    brand_record=brand_context_index.get(brand_key),
                )
            qwen_result = run_qwen_logo_reasoning(qwen_engine, prompt_payload)
            qwen_payload = {"mode": "multi_section", "prompt_payload": prompt_payload, "sections": qwen_result["section_traces"]}
            qwen_structured = qwen_result["split_payload"]

        merged = merge_signals(
            {
                **record,
                "logo_detection_score": detection["detector_score"],
                "logo_grounding_label": detection["detector_label"],
                "ocr_text": ocr_payload.get("text"),
            },
            brand_index,
            ocr_payload=ocr_payload,
            clip_payload=clip_payload,
            caption_payload=vlm_payload or caption_payload,
        )

        if merged.get("merged_brand_id") and str(merged["merged_brand_id"]) not in known_brand_ids:
            merged["merged_brand_id"] = None

        proposal = {
            "bbox_xyxy": detection["bbox_xyxy"] or None,
            "brand": merged["merged_brand_name"],
            "grounding_label": detection["detector_label"],
        }
        instance_id = logo_instance_id(str(row["image_id"]), proposal)
        if resume and instance_id in existing_instance_ids:
            skipped_existing += 1
            continue

        verification_payload = verify_text_consistency(
            record=record,
            merged=merged,
            brand_record=brand_context_index.get(brand_key),
            qwen_structured=qwen_structured,
        )
        if verification_payload["overall_status"] == "conflict":
            verification_conflicts += 1
        final_confidence = round((float(merged["confidence"] or 0.0) * 0.7) + (float(verification_payload["verification_score"] or 0.0) * 0.3), 4)
        review_policy = classify_review_bucket(
            confidence=final_confidence,
            verification_payload=verification_payload,
            brand_id=merged.get("merged_brand_id"),
        )
        review_bucket_counts[review_policy["review_bucket"]] = review_bucket_counts.get(review_policy["review_bucket"], 0) + 1

        now = utcnow_iso()
        rows.append(
            {
                "instance_id": instance_id,
                "image_id": row["image_id"],
                "brand_id": merged["merged_brand_id"],
                "merged_brand_name": merged["merged_brand_name"],
                "detector_name": detection["detector_name"],
                "ocr_engine": ocr_payload.get("engine"),
                "clip_engine": merged["clip"]["engine"],
                "bbox_json": json_text(detection["bbox_xyxy"]) if detection["bbox_xyxy"] else None,
                "polygon_json": None,
                "rotated_box_json": None,
                "mask_path": None,
                "detector_score": detection["detector_score"] if detection["bbox_xyxy"] else None,
                "ocr_text": ocr_payload.get("text"),
                "ocr_confidence": ocr_payload.get("confidence"),
                "clip_score": merged["clip"]["score"],
                "caption_text": (
                    (vlm_payload or caption_payload or {}).get("logo_crop_caption")
                    or (vlm_payload or caption_payload or {}).get("full_image_caption")
                ),
                "caption_model": (vlm_payload or caption_payload or {}).get("model_id"),
                "attribution_json": json_text(
                    {
                        "source": merged.get("attribution_source"),
                        "clip_retrieval": clip_payload,
                        "captioning": vlm_payload or caption_payload,
                        "qwen_knowledge": qwen_payload,
                        "qwen_validation": (qwen_structured or {}).get("validation"),
                        "merged": {
                            "brand_id": merged.get("merged_brand_id"),
                            "brand_name": merged.get("merged_brand_name"),
                            "confidence": merged.get("confidence"),
                            "ambiguity_note": merged.get("ambiguity_note"),
                        },
                    }
                ),
                "knowledge_json": json_text((qwen_structured or {}).get("knowledge_json")) if qwen_structured else None,
                "risk_json": json_text((qwen_structured or {}).get("risk_json")) if qwen_structured else None,
                "verification_json": json_text(verification_payload),
                "confidence": final_confidence,
                "ambiguity_note": merged["ambiguity_note"] or ("verification_conflict" if verification_payload["overall_status"] == "conflict" else None),
                "review_status": review_policy["review_status"],
                "review_bucket": review_policy["review_bucket"],
                "tier": tier,
                "provenance_json": json_text(
                    {
                        "source": "engine_annotate_db",
                        "detector_label": detection["detector_label"],
                        "prompt_context": detection["prompt_context"],
                        "prompt_variants": detection["prompt_variants"],
                        "ocr_lines": ocr_payload.get("lines"),
                        "ocr_error": ocr_payload.get("error"),
                        "attribution_source": merged.get("attribution_source"),
                        "caption_payload": vlm_payload or caption_payload,
                        "qwen_payload": qwen_payload,
                        "clip_retrieval": clip_payload,
                        "qwen_structured": qwen_structured,
                        "text_only_mode": detection["detector_name"] == "text_only_metadata",
                    }
                ),
                "raw_json": json_text({"record": record, "detection": detection, "merged": merged}),
                "created_at": now,
                "updated_at": now,
            }
        )

    if not dry_run:
        with db.transaction():
            db.upsert_logo_instances(rows, commit=False)
            db.record_stage_metric(
                "annotate_db",
                {
                    "seen_images": len(image_rows),
                    "inserted_instances": len(rows),
                    "skipped_existing": skipped_existing,
                    "detector_failures": detector_failures,
                    "text_only_instances": text_only_instances,
                    "verification_conflicts": verification_conflicts,
                    "review_bucket_counts": review_bucket_counts,
                },
                command_name="annotate-db",
                commit=False,
            )
    return {
        "seen_images": len(image_rows),
        "inserted_instances": len(rows),
        "skipped_existing": skipped_existing,
        "detector_failures": detector_failures,
        "text_only_instances": text_only_instances,
        "verification_conflicts": verification_conflicts,
        "review_bucket_counts": review_bucket_counts,
        "detector_available": None if detector is None else detector.available,
        "detector_error": "disabled" if detector is None else detector.error,
        "ocr_available": None if ocr_engine is None else ocr_engine.available,
        "ocr_error": "disabled" if ocr_engine is None else ocr_engine.error,
        "clip_retrieval_available": None if skip_clip_retrieval else clip_retriever.available,
        "clip_retrieval_error": None if skip_clip_retrieval else clip_retriever.error,
        "captioning_available": None if skip_captioning else captioner.available,
        "captioning_error": None if skip_captioning else captioner.error,
        "vlm_available": vlm_engine.available if vlm_engine is not None else None,
        "vlm_error": vlm_engine.error if vlm_engine is not None else None,
        "qwen_available": qwen_engine.available if qwen_engine is not None else None,
        "qwen_error": qwen_engine.error if qwen_engine is not None else None,
    }
