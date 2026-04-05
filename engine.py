from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .annotations import imported_logo_instances, merge_signals
from .db import EngineDB
from .dedupe import compute_phash
from .qwen_reasoning import build_qwen_prompt_payload, run_qwen_logo_reasoning
from .record_types import BrandCatalogEntry, BrandKnowledgeRecord, BrandRow, ImageRow, LogoInstanceRow, ProductRecord
from .schema import (
    canonical_brand_id,
    image_external_key,
    image_id_from_record,
    json_text,
    logo_instance_id,
    resolve_local_path,
    scene_bucket_from_record,
    utcnow_iso,
)
from .verifier import classify_review_bucket, verify_text_consistency


def load_json_list(path: str | Path) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Expected a JSON list in {path}")
    return payload


def load_run_payloads(run_dir: str | Path) -> Dict[str, List[Dict[str, Any]]]:
    run_path = Path(run_dir)
    return {
        "brands": load_json_list(run_path / "brand" / "brand_records.json"),
        "images": load_json_list(run_path / "fetch" / "records.json"),
        "segments": load_json_list(run_path / "segment" / "records_with_logo_masks.json"),
    }


def brand_context_by_id(db: EngineDB) -> Dict[str, Dict[str, Any]]:
    rows = db.conn.execute("SELECT brand_id, knowledge_json FROM brand_records").fetchall()
    context: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        payload = json.loads(str(row["knowledge_json"]))
        context[str(row["brand_id"])] = payload
    return context


def brand_rows_from_records(brand_records: Iterable[BrandKnowledgeRecord], tier: str) -> List[BrandRow]:
    now = utcnow_iso()
    rows: List[BrandRow] = []
    for record in brand_records:
        if not record.get("matched"):
            continue
        display_name = str(record.get("label") or record.get("query") or "").strip()
        if not display_name:
            continue
        rows.append(
            {
                "brand_id": canonical_brand_id(display_name),
                "canonical_name": display_name.lower(),
                "display_name": display_name,
                "tier": tier,
                "industry": ((record.get("industries") or [None])[0]),
                "country": ((record.get("countries") or [None])[0]),
                "parent_company": ((record.get("parent_organizations") or [None])[0]),
                "knowledge_json": json_text(record),
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


def ingest_image_records(
    db: EngineDB,
    records: Iterable[ProductRecord],
    tier: str,
    dry_run: bool = False,
    resume: bool = False,
) -> Dict[str, int]:
    now = utcnow_iso()
    existing_phashes = db.existing_phashes()
    existing_keys = db.existing_external_keys()
    batch_phashes: set[str] = set()
    rows: List[ImageRow] = []
    stats = {"seen": 0, "inserted": 0, "skipped_existing": 0, "skipped_duplicate": 0, "phash_failures": 0}

    for record in records:
        stats["seen"] += 1
        external_key = image_external_key(record)
        if resume and external_key in existing_keys:
            stats["skipped_existing"] += 1
            continue

        local_image_path = resolve_local_path(record.get("local_image_path"))
        image_phash = None
        if local_image_path and Path(local_image_path).exists():
            try:
                image_phash = compute_phash(local_image_path)
            except Exception:
                stats["phash_failures"] += 1
        if image_phash and (image_phash in existing_phashes or image_phash in batch_phashes):
            stats["skipped_duplicate"] += 1
            continue
        if image_phash:
            batch_phashes.add(image_phash)

        image_id = image_id_from_record(record)
        rows.append(
            {
                "image_id": image_id,
                "external_key": external_key,
                "brand_hint": record.get("brand"),
                "category": record.get("category"),
                "source_name": record.get("source"),
                "source_channel": record.get("source_channel"),
                "source_kind": record.get("source_kind"),
                "scene_bucket": scene_bucket_from_record(record),
                "image_url": record.get("image_url"),
                "local_image_path": local_image_path,
                "image_phash": image_phash,
                "quality_status": None,
                "quality_score": None,
                "quality_gate_json": None,
                "difficulty_flags_json": None,
                "last_gated_at": None,
                "tier": tier,
                "capture_context_json": json_text(record.get("capture_context") or {}),
                "raw_json": json_text(record),
                "created_at": now,
                "updated_at": now,
            }
        )
    stats["inserted"] = len(rows)
    if not dry_run:
        with db.transaction():
            db.upsert_image_records(rows, commit=False)
            db.record_stage_metric("ingest_images", stats, command_name="ingest-images", commit=False)
    return stats


def annotate_from_segment_records(
    db: EngineDB,
    segment_records: Iterable[ProductRecord],
    tier: str,
    dry_run: bool = False,
    resume: bool = False,
    enrich: bool = False,
    brand_catalog: List[BrandCatalogEntry] | None = None,
    clip_retrieval_model_id: str = "openai/clip-vit-base-patch32",
    caption_model_id: str = "Salesforce/blip-image-captioning-base",
    skip_ocr: bool = False,
    skip_clip_retrieval: bool = False,
    skip_captioning: bool = False,
    vlm_model_id: str = "llava-hf/llava-1.5-7b-hf",
    use_vlm: bool = False,
    use_qwen_qa: bool = False,
    qwen_model_id: str = "Qwen/Qwen2.5-7B-Instruct",
) -> Dict[str, int]:
    segment_records = list(segment_records)
    existing_instance_ids = db.existing_instance_ids()
    image_rows = db.conn.execute(
        "SELECT image_id, external_key, local_image_path, quality_status FROM image_records"
    ).fetchall()
    image_id_by_external_key = {
        str(row["external_key"]): {
            "image_id": str(row["image_id"]),
            "local_image_path": row["local_image_path"],
            "quality_status": row["quality_status"],
        }
        for row in image_rows
    }
    brand_index = db.brand_name_index()
    known_brand_ids = db.brand_ids()
    brand_context = brand_context_by_id(db)

    if not enrich:
        rows = imported_logo_instances(segment_records, {k: v["image_id"] for k, v in image_id_by_external_key.items()}, brand_index, tier=tier)
    else:
        from PIL import Image

        from .backends import BLIPCaptionEngine, CLIPBrandRetriever, LLaMAVLMEngine, PaddleOCREngine, QwenKnowledgeEngine

        ocr_engine = None if skip_ocr else PaddleOCREngine(lang="en")
        clip_retriever = None if skip_clip_retrieval else CLIPBrandRetriever(model_id=clip_retrieval_model_id)
        captioner = None if skip_captioning else BLIPCaptionEngine(model_id=caption_model_id)
        vlm_engine = LLaMAVLMEngine(model_id=vlm_model_id) if use_vlm else None
        qwen_engine = QwenKnowledgeEngine(model_id=qwen_model_id) if use_qwen_qa else None
        catalog = brand_catalog or []
        rows: List[LogoInstanceRow] = []
        timestamp = utcnow_iso()

        for record in segment_records:
            if record.get("logo_segmentation_status") != "ok":
                continue
            external_key = image_external_key(record)
            image_info = image_id_by_external_key.get(external_key)
            if not image_info:
                continue
            image_id = image_info["image_id"]
            image_path = resolve_local_path(record.get("local_image_path") or image_info.get("local_image_path"))
            if not image_path or not Path(image_path).exists():
                continue

            bbox = record.get("logo_bbox_xyxy") or record.get("logo_grounding_bbox_xyxy")
            if not bbox:
                continue

            with Image.open(image_path) as image:
                image = image.convert("RGB")
                x0, y0, x1, y1 = [int(round(v)) for v in bbox]
                left = max(0, min(image.width, x0))
                upper = max(0, min(image.height, y0))
                right = max(left + 1, min(image.width, x1))
                lower = max(upper + 1, min(image.height, y1))
                crop = image.crop((left, upper, right, lower))

                if ocr_engine is None:
                    ocr_payload = {
                        "engine": "paddleocr",
                        "text": None,
                        "confidence": 0.0,
                        "lines": [],
                        "error": "disabled",
                    }
                else:
                    ocr_payload = ocr_engine.recognize(image_path, crop_box_xyxy=bbox)
                clip_payload = None
                if clip_retriever is not None and clip_retriever.available:
                    clip_payload = clip_retriever.retrieve(
                        crop,
                        catalog,
                        object_hint=str(record.get("category") or "").strip().lower() or None,
                    )

                caption_payload = None
                vlm_payload = None
                qwen_payload = None
                if vlm_engine is not None and vlm_engine.available and str(image_info.get("quality_status") or "") == "passed":
                    full_caption = vlm_engine.caption(image, prompt="Describe the brand, object, and photo scene.")
                    crop_caption = vlm_engine.caption(crop, prompt="Describe the logo, brand, and object in this crop.")
                    vlm_payload = {
                        "model_id": vlm_engine.model_id,
                        "full_image_caption": full_caption.get("text"),
                        "logo_crop_caption": crop_caption.get("text"),
                        "full_image_prompt": full_caption.get("prompt"),
                        "logo_crop_prompt": crop_caption.get("prompt"),
                        "full_image_error": full_caption.get("error"),
                        "logo_crop_error": crop_caption.get("error"),
                    }
                if captioner is not None and captioner.available and str(image_info.get("quality_status") or "") == "passed":
                    full_caption = captioner.caption(image, prompt="Describe the brand, object, and photo scene.")
                    crop_caption = captioner.caption(crop, prompt="Describe the logo, brand, and object in this crop.")
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
                if qwen_engine is not None and qwen_engine.available and str(image_info.get("quality_status") or "") == "passed":
                    prompt_payload = build_qwen_prompt_payload(
                        brand_hint=record.get("brand"),
                        category=record.get("category"),
                        source_channel=record.get("source_channel"),
                        scene_bucket=record.get("scene_bucket"),
                        quality_status=image_info.get("quality_status"),
                        bbox_xyxy=bbox,
                        ocr_text=ocr_payload.get("text"),
                        clip_matches=(clip_payload or {}).get("matches") if clip_payload else None,
                        caption=(vlm_payload or caption_payload or {}).get("logo_crop_caption")
                        or (vlm_payload or caption_payload or {}).get("full_image_caption"),
                        brand_record=None,
                    )
                    qwen_result = run_qwen_logo_reasoning(qwen_engine, prompt_payload)
                    qwen_payload = {"mode": "multi_section", "prompt_payload": prompt_payload, "sections": qwen_result["section_traces"]}
                    qwen_structured = qwen_result["split_payload"]

            merged = merge_signals(
                {
                    **record,
                    "logo_detection_score": float(record.get("logo_detection_score") or record.get("logo_grounding_score") or 0.0),
                    "logo_grounding_label": record.get("logo_grounding_label"),
                    "ocr_text": ocr_payload.get("text") if ocr_payload else None,
                },
                brand_index,
                ocr_payload=ocr_payload,
                clip_payload=clip_payload,
                caption_payload=vlm_payload or caption_payload,
            )
            if merged.get("merged_brand_id") and str(merged["merged_brand_id"]) not in known_brand_ids:
                merged["merged_brand_id"] = None

            proposal = {
                "bbox_xyxy": bbox,
                "mask_path": record.get("logo_mask_path"),
                "brand": merged["merged_brand_name"],
                "grounding_label": record.get("logo_grounding_label"),
            }
            instance_id = logo_instance_id(image_id, proposal)
            verification_payload = verify_text_consistency(
                record=record,
                merged=merged,
                brand_record=brand_context.get(str(merged.get("merged_brand_id") or "")),
                qwen_structured=qwen_structured,
            )
            final_confidence = round((float(merged["confidence"] or 0.0) * 0.7) + (float(verification_payload["verification_score"] or 0.0) * 0.3), 4)
            review_policy = classify_review_bucket(
                confidence=final_confidence,
                verification_payload=verification_payload,
                brand_id=merged.get("merged_brand_id"),
            )

            rows.append(
                {
                    "instance_id": instance_id,
                    "image_id": image_id,
                    "brand_id": merged["merged_brand_id"],
                    "merged_brand_name": merged["merged_brand_name"],
                    "detector_name": "imported_grounding_sam3",
                    "ocr_engine": ocr_payload.get("engine") if ocr_payload else None,
                    "clip_engine": merged["clip"]["engine"],
                    "bbox_json": json_text(bbox),
                    "polygon_json": None,
                    "rotated_box_json": None,
                    "mask_path": record.get("logo_mask_path"),
                    "detector_score": float(record.get("logo_detection_score") or record.get("logo_grounding_score") or 0.0),
                    "ocr_text": ocr_payload.get("text") if ocr_payload else None,
                    "ocr_confidence": ocr_payload.get("confidence") if ocr_payload else None,
                    "clip_score": merged["clip"]["score"],
                    "caption_text": (vlm_payload or caption_payload or {}).get("logo_crop_caption") or (vlm_payload or caption_payload or {}).get("full_image_caption"),
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
                            "source": "imported_segment_records",
                            "logo_grounding_model_id": record.get("logo_grounding_model_id"),
                            "logo_prompt_context": record.get("logo_prompt_context"),
                            "logo_visualization_path": record.get("logo_visualization_path"),
                            "attribution_source": merged.get("attribution_source"),
                            "qwen_payload": qwen_payload,
                            "qwen_structured": qwen_structured,
                        }
                    ),
                    "raw_json": json_text(record),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
    skipped_existing = 0
    if resume:
        skipped_existing = sum(1 for row in rows if str(row["instance_id"]) in existing_instance_ids)
        rows = [row for row in rows if str(row["instance_id"]) not in existing_instance_ids]
    stats = {
        "seen": len(segment_records),
        "inserted": len(rows),
        "skipped_existing": skipped_existing,
    }
    if not dry_run:
        with db.transaction():
            db.upsert_logo_instances(rows, commit=False)
            db.record_stage_metric("annotate_segments", stats, command_name="annotate-proposals", commit=False)
    return stats


def import_run(
    db: EngineDB,
    run_dir: str | Path,
    image_tier: str = "proposal",
    brand_tier: str = "silver",
    instance_tier: str = "proposal",
    dry_run: bool = False,
    resume: bool = False,
) -> Dict[str, Any]:
    payloads = load_run_payloads(run_dir)
    brand_rows = brand_rows_from_records(payloads["brands"], tier=brand_tier)
    if not dry_run:
        with db.transaction():
            db.upsert_brand_records(brand_rows, commit=False)

    image_stats = ingest_image_records(db, payloads["images"], tier=image_tier, dry_run=dry_run, resume=resume)
    instance_stats = annotate_from_segment_records(
        db,
        payloads["segments"],
        tier=instance_tier,
        dry_run=dry_run,
        resume=resume,
    )
    return {
        "brand_records": len(brand_rows),
        "image_records": image_stats,
        "logo_instances": instance_stats,
    }


def export_joined_records(db: EngineDB, output_path: str | Path, dry_run: bool = False) -> Dict[str, Any]:
    path = Path(output_path)
    record_count = db.table_counts()["image_records"]
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write("[\n")
            wrote_any = False
            for row in db.iter_joined_records():
                if wrote_any:
                    handle.write(",\n")
                handle.write(json.dumps(row, ensure_ascii=False, indent=2))
                wrote_any = True
            handle.write("\n]\n")
    return {"output": str(path), "records": record_count}
