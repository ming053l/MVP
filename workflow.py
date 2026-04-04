from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from PIL import Image
import torch

from .annotations import merge_signals
from .backends import (
    BLIPCaptionEngine,
    LLaMAVLMEngine,
    CLIPLogoQualityScorer,
    CLIPBrandRetriever,
    GroundingDINOProposalDetector,
    PaddleOCREngine,
    QwenKnowledgeEngine,
    YOLOWorldLogoPrescreener,
)
from .db import EngineDB
from .engine import annotate_from_segment_records, brand_rows_from_records, ingest_image_records, load_json_list
from .quality import evaluate_image_quality, gate_report
from .qwen_reasoning import build_qwen_prompt_payload, run_qwen_logo_reasoning
from .schema import canonical_brand_id, json_text, logo_instance_id, utcnow_iso


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_command(cmd: List[str], cwd: Optional[Path] = None, dry_run: bool = False) -> None:
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd or repo_root()), check=True)


def preflight_models(
    *,
    with_sam3: bool = False,
    sam3_checkpoint: str | None = None,
    sam3_device: str | None = None,
    object_first: bool = True,
    grounding_model_id: str = "IDEA-Research/grounding-dino-tiny",
    grounding_threshold: float = 0.2,
    grounding_text_threshold: float = 0.2,
    grounding_max_candidates: int = 6,
    use_vlm: bool = False,
    vlm_model_id: str = "llava-hf/llava-1.5-7b-hf",
    use_qwen_qa: bool = False,
    qwen_model_id: str = "Qwen/Qwen2.5-7B-Instruct",
    skip_detector: bool = False,
    skip_ocr: bool = False,
    skip_clip: bool = False,
    skip_clip_retrieval: bool = False,
    skip_captioning: bool = False,
    skip_prescreen: bool = False,
    prescreen_threshold: float = 0.3,
) -> Dict[str, Any]:
    statuses: Dict[str, Any] = {"with_sam3": with_sam3, "use_vlm": use_vlm}

    detector = None if skip_detector else GroundingDINOProposalDetector(model_id=grounding_model_id)
    statuses["grounding_dino"] = {
        "enabled": not skip_detector,
        "available": None if detector is None else detector.available,
        "error": "disabled" if detector is None else detector.error,
        "model_id": grounding_model_id,
    }

    ocr_engine = None if skip_ocr else PaddleOCREngine(lang="en")
    statuses["paddleocr"] = {
        "enabled": not skip_ocr,
        "available": None if ocr_engine is None else ocr_engine.available,
        "error": "disabled" if ocr_engine is None else ocr_engine.error,
    }

    clip_scorer = None if skip_clip else CLIPLogoQualityScorer()
    statuses["clip_logo_gate"] = {
        "enabled": not skip_clip,
        "available": None if clip_scorer is None else clip_scorer.available,
        "error": "disabled" if clip_scorer is None else clip_scorer.error,
    }

    clip_retriever = None if skip_clip_retrieval else CLIPBrandRetriever()
    statuses["clip_retrieval"] = {
        "enabled": not skip_clip_retrieval,
        "available": None if clip_retriever is None else clip_retriever.available,
        "error": "disabled" if clip_retriever is None else clip_retriever.error,
    }

    captioner = None if skip_captioning else BLIPCaptionEngine()
    statuses["blip_caption"] = {
        "enabled": not skip_captioning,
        "available": None if captioner is None else captioner.available,
        "error": "disabled" if captioner is None else captioner.error,
    }

    vlm_engine = None
    if use_vlm:
        vlm_engine = LLaMAVLMEngine(model_id=vlm_model_id)
    statuses["vlm"] = {
        "enabled": use_vlm,
        "available": None if vlm_engine is None else vlm_engine.available,
        "error": None if vlm_engine is None else vlm_engine.error,
        "model_id": vlm_model_id if use_vlm else None,
    }
    qwen_engine = None
    if use_qwen_qa:
        qwen_engine = QwenKnowledgeEngine(model_id=qwen_model_id)
    statuses["qwen_qa"] = {
        "enabled": use_qwen_qa,
        "available": None if qwen_engine is None else qwen_engine.available,
        "error": None if qwen_engine is None else qwen_engine.error,
        "model_id": qwen_model_id if use_qwen_qa else None,
    }

    prescreener = None if skip_prescreen else YOLOWorldLogoPrescreener(conf_threshold=prescreen_threshold)
    statuses["yolo_prescreen"] = {
        "enabled": not skip_prescreen,
        "available": None if prescreener is None else prescreener.available,
        "error": "disabled" if prescreener is None else prescreener.error,
        "threshold": prescreen_threshold,
    }

    if with_sam3:
        try:
            from logo_segmentation_pipeline import Sam3LogoSegmenter

            segmenter = Sam3LogoSegmenter(
                checkpoint_path=sam3_checkpoint,
                device=sam3_device or ("cuda" if torch.cuda.is_available() else "cpu"),
                confidence_threshold=0.35,
                grounding_model_id=grounding_model_id,
                grounding_threshold=grounding_threshold,
                grounding_text_threshold=grounding_text_threshold,
                grounding_max_candidates=grounding_max_candidates,
                object_first=object_first,
            )
            statuses["sam3"] = {
                "enabled": True,
                "available": segmenter.available,
                "error": segmenter.unavailable_reason,
                "checkpoint": sam3_checkpoint,
                "device": sam3_device or ("cuda" if torch.cuda.is_available() else "cpu"),
                "object_first": object_first,
            }
        except Exception as exc:  # pragma: no cover
            statuses["sam3"] = {
                "enabled": True,
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
                "checkpoint": sam3_checkpoint,
                "device": sam3_device,
                "object_first": object_first,
            }
    else:
        statuses["sam3"] = {"enabled": False, "available": None, "error": "disabled"}

    return statuses


def collector_fetch_products(
    output_path: str | Path,
    image_dir: str | Path,
    *,
    all_pairs: bool = False,
    brands: Optional[str] = None,
    categories: Optional[str] = None,
    limit: int = 4,
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = repo_root()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(image_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(root / "multi_brand_fetcher.py"),
        "--output",
        str(output_path),
        "--image-dir",
        str(image_dir),
        "--limit",
        str(limit),
    ]
    if all_pairs:
        cmd.append("--all")
    else:
        if not brands or not categories:
            raise ValueError("brands and categories are required unless all_pairs=True")
        cmd.extend(["--brands", brands, "--categories", categories])
    run_command(cmd, cwd=root, dry_run=dry_run)
    return {"output": str(output_path), "image_dir": str(image_dir), "dry_run": dry_run}


def collector_prepare_external_records(
    collection_root: str | Path,
    output_path: str | Path,
    *,
    metadata_csv: str | Path | None = None,
    default_source: str | None = None,
    default_source_channel: str | None = None,
    default_license: str = "unknown",
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = repo_root()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(root / "prepare_external_records.py"),
        "--collection-root",
        str(collection_root),
        "--output",
        str(output_path),
        "--default-license",
        default_license,
    ]
    if metadata_csv:
        cmd.extend(["--metadata-csv", str(metadata_csv)])
    if default_source:
        cmd.extend(["--default-source", default_source])
    if default_source_channel:
        cmd.extend(["--default-source-channel", default_source_channel])
    run_command(cmd, cwd=root, dry_run=dry_run)
    return {"output": str(output_path), "collection_root": str(collection_root), "dry_run": dry_run}


def collector_ingest_external_manifests(
    manifests: Iterable[str | Path],
    output_path: str | Path,
    image_dir: str | Path,
    *,
    default_license: str = "unknown",
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = repo_root()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(image_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(root / "ingest_external_records.py"),
        "--output",
        str(output_path),
        "--image-dir",
        str(image_dir),
        "--default-license",
        default_license,
    ]
    for manifest in manifests:
        cmd.extend(["--manifest", str(manifest)])
    run_command(cmd, cwd=root, dry_run=dry_run)
    return {"output": str(output_path), "image_dir": str(image_dir), "dry_run": dry_run}


def ontology_fetch_brand_records(
    product_records_path: str | Path,
    output_path: str | Path,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = repo_root()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(root / "brand_data_fetcher.py"),
        "--product-records",
        str(product_records_path),
        "--output",
        str(output_path),
    ]
    run_command(cmd, cwd=root, dry_run=dry_run)
    return {"output": str(output_path), "dry_run": dry_run}


def segment_with_sam3(
    *,
    input_records: str | Path,
    output_records: str | Path,
    mask_dir: str | Path,
    viz_dir: str | Path,
    brand_records: str | Path | None = None,
    checkpoint_path: str | None = None,
    device: str | None = None,
    max_records: int | None = None,
    object_first: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = repo_root()
    Path(output_records).parent.mkdir(parents=True, exist_ok=True)
    Path(mask_dir).mkdir(parents=True, exist_ok=True)
    Path(viz_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(root / "logo_segmentation_pipeline.py"),
        "--input-records",
        str(input_records),
        "--output",
        str(output_records),
        "--mask-dir",
        str(mask_dir),
        "--viz-dir",
        str(viz_dir),
    ]
    if brand_records:
        cmd.extend(["--brand-records", str(brand_records)])
    if checkpoint_path:
        cmd.extend(["--checkpoint-path", str(checkpoint_path)])
    if device:
        cmd.extend(["--device", str(device)])
    if max_records is not None:
        cmd.extend(["--max-records", str(int(max_records))])
    if not object_first:
        cmd.append("--no-object-first")
    run_command(cmd, cwd=root, dry_run=dry_run)
    return {
        "input_records": str(input_records),
        "output_records": str(output_records),
        "mask_dir": str(mask_dir),
        "viz_dir": str(viz_dir),
        "dry_run": dry_run,
    }


def seed_ontology_from_json(db: EngineDB, brand_records_path: str | Path, tier: str = "silver", dry_run: bool = False) -> Dict[str, Any]:
    brand_rows = brand_rows_from_records(load_json_list(brand_records_path), tier=tier)
    if not dry_run:
        db.upsert_brand_records(brand_rows)
    return {"inserted": len(brand_rows), "tier": tier, "dry_run": dry_run}


def brand_context_from_db(db: EngineDB) -> Dict[str, Dict[str, Any]]:
    rows = db.conn.execute("SELECT canonical_name, display_name, knowledge_json FROM brand_records").fetchall()
    context = {}
    for row in rows:
        payload = json.loads(str(row["knowledge_json"]))
        for key in (row["canonical_name"], row["display_name"], payload.get("query"), payload.get("label")):
            if key:
                context[str(key).strip().lower()] = payload
        for alias in payload.get("aliases_en") or []:
            if alias:
                context[str(alias).strip().lower()] = payload
    return context


def brand_catalog_from_db(db: EngineDB) -> List[Dict[str, Any]]:
    rows = db.conn.execute("SELECT brand_id, canonical_name, display_name, knowledge_json FROM brand_records ORDER BY display_name").fetchall()
    catalog: List[Dict[str, Any]] = []
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
    record: Dict[str, Any],
    brand_context: Optional[Dict[str, Any]],
    detector: GroundingDINOProposalDetector,
    ocr_engine: PaddleOCREngine | None,
    skip_ocr: bool = False,
) -> Optional[Dict[str, Any]]:
    from logo_segmentation_pipeline import build_prompts

    with Image.open(image_path) as image:
        image = image.convert("RGB")
        prompts, prompt_context = build_prompts(record, brand_context)
        candidates = detector.detect(image, prompts, prompt_context["expected_logo_fraction_range"])
        if not candidates:
            return None
        best = candidates[0]
    if skip_ocr or ocr_engine is None:
        ocr_result = {
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
    rows = []
    skipped_existing = 0
    detector_failures = 0
    for row in image_rows:
        record = json.loads(str(row["raw_json"]))
        image_path = row["local_image_path"]
        if not image_path or not Path(str(image_path)).exists():
            continue
        if detector is None or not detector.available:
            detector_failures += 1
            continue
        brand_key = str(record.get("brand") or row["brand_hint"] or "").strip().lower()
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
            continue

        ocr_payload = dict(detection["ocr"])
        clip_payload = None
        caption_payload = None
        vlm_payload = None
        qwen_payload = None
        image = None
        if (
            (clip_retriever is not None and clip_retriever.available)
            or (captioner is not None and captioner.available)
            or (vlm_engine is not None and vlm_engine.available)
        ):
            with Image.open(image_path) as opened:
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

        qwen_payload = None
        qwen_structured = None
        if qwen_engine is not None and qwen_engine.available and str(row["quality_status"] or "") == "passed":
            brand_key = str(record.get("brand") or row["brand_hint"] or "").strip().lower()
            brand_context = brand_context_index.get(brand_key) or {}
            prompt_payload = build_qwen_prompt_payload(
                brand_hint=record.get("brand") or row["brand_hint"],
                category=record.get("category"),
                source_channel=record.get("source_channel") or row["source_channel"],
                scene_bucket=record.get("scene_bucket"),
                quality_status=row["quality_status"],
                bbox_xyxy=detection.get("bbox_xyxy"),
                ocr_text=ocr_payload.get("text"),
                clip_matches=(clip_payload or {}).get("matches") if clip_payload else None,
                caption=(vlm_payload or caption_payload or {}).get("logo_crop_caption")
                or (vlm_payload or caption_payload or {}).get("full_image_caption"),
                brand_record=brand_context or None,
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
            "bbox_xyxy": detection["bbox_xyxy"],
            "brand": merged["merged_brand_name"],
            "grounding_label": detection["detector_label"],
        }
        instance_id = logo_instance_id(str(row["image_id"]), proposal)
        if resume and instance_id in existing_instance_ids:
            skipped_existing += 1
            continue

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
                "bbox_json": json_text(detection["bbox_xyxy"]),
                "polygon_json": None,
                "rotated_box_json": None,
                "mask_path": None,
                "detector_score": detection["detector_score"],
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
                "confidence": merged["confidence"],
                "ambiguity_note": merged["ambiguity_note"],
                "review_status": "needs_review" if merged["confidence"] < 0.9 else "auto_accept",
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
                    }
                ),
                "raw_json": json_text({"record": record, "detection": detection, "merged": merged}),
                "created_at": now,
                "updated_at": now,
            }
        )

    if not dry_run:
        db.upsert_logo_instances(rows)
    return {
        "seen_images": len(image_rows),
        "inserted_instances": len(rows),
        "skipped_existing": skipped_existing,
        "detector_failures": detector_failures,
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


def gate_images(
    db: EngineDB,
    *,
    limit: Optional[int] = None,
    source_channel: Optional[str] = None,
    dry_run: bool = False,
    resume: bool = False,
    report: bool = False,
    min_width: int = 256,
    min_height: int = 256,
    blur_threshold: float = 45.0,
    clip_threshold: float = 0.22,
    clip_soft_floor: float = 0.08,
    phash_distance_threshold: int = 6,
    skip_clip: bool = False,
    skip_prescreen: bool = False,
    prescreen_threshold: float = 0.3,
) -> Dict[str, Any]:
    clip_scorer = None if skip_clip else CLIPLogoQualityScorer()
    prescreener = None if skip_prescreen else YOLOWorldLogoPrescreener(conf_threshold=prescreen_threshold)
    accepted_phashes = db.quality_passed_phashes()

    query = """
        SELECT image_id, local_image_path, image_phash, raw_json, quality_status
        FROM image_records
    """
    conditions = []
    params: List[Any] = []
    if source_channel:
        conditions.append("source_channel = ?")
        params.append(source_channel)
    if resume:
        conditions.append("(quality_status IS NULL OR quality_status = 'pending')")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at, image_id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    image_rows = db.conn.execute(query, params).fetchall()
    updates = []
    evaluated = []
    for row in image_rows:
        record = json.loads(str(row["raw_json"]))
        result = evaluate_image_quality(
            image_id=str(row["image_id"]),
            record=record,
            image_path=str(row["local_image_path"] or ""),
            image_phash=str(row["image_phash"]) if row["image_phash"] else None,
            accepted_phashes=accepted_phashes,
            clip_scorer=clip_scorer,
            prescreener=prescreener,
            min_width=min_width,
            min_height=min_height,
            blur_threshold=blur_threshold,
            clip_threshold=clip_threshold,
            clip_soft_floor=clip_soft_floor,
            phash_distance_threshold=phash_distance_threshold,
        )
        evaluated.append(result)
        if result["quality_status"] == "passed" and row["image_phash"]:
            accepted_phashes.append(str(row["image_phash"]))
        updates.append(
            {
                "image_id": result["image_id"],
                "quality_status": result["quality_status"],
                "quality_score": result["quality_score"],
                "quality_gate_json": result["quality_gate_json"],
                "difficulty_flags_json": result["difficulty_flags_json"],
                "last_gated_at": result["last_gated_at"],
                "updated_at": result["updated_at"],
            }
        )

    if not dry_run:
        db.update_image_quality(updates)

    summary = gate_report(evaluated)
    result = {
        "seen_images": len(image_rows),
        "updated_images": len(updates),
        "dry_run": dry_run,
        "resume": resume,
        "clip_available": None if skip_clip else clip_scorer.available,
        "clip_error": None if skip_clip else clip_scorer.error,
        "prescreener_available": None if skip_prescreen else prescreener.available,
        "prescreener_error": None if skip_prescreen else prescreener.error,
        "quality_status_counts": db.quality_status_counts() if not dry_run else summary["status_counts"],
    }
    if report:
        result["report"] = summary
    return result


def review_queue(
    db: EngineDB,
    output_path: str | Path,
    *,
    limit: int = 200,
    dry_run: bool = False,
) -> Dict[str, Any]:
    rows = db.conn.execute(
        """
        SELECT li.instance_id, li.image_id, li.merged_brand_name, li.detector_score,
               li.ocr_text, li.ocr_confidence, li.clip_score, li.confidence, li.review_status,
               li.tier, ir.local_image_path, ir.source_channel, ir.scene_bucket, ir.raw_json
        FROM logo_instances li
        JOIN image_records ir ON ir.image_id = li.image_id
        WHERE li.review_status IS NULL OR li.review_status != 'auto_accept'
        ORDER BY COALESCE(li.confidence, 0.0) ASC, li.created_at ASC
        LIMIT ?
        """,
        [int(limit)],
    ).fetchall()
    queue = []
    for row in rows:
        queue.append(
            {
                "instance_id": row["instance_id"],
                "image_id": row["image_id"],
                "brand": row["merged_brand_name"],
                "detector_score": row["detector_score"],
                "ocr_text": row["ocr_text"],
                "ocr_confidence": row["ocr_confidence"],
                "clip_score": row["clip_score"],
                "confidence": row["confidence"],
                "review_status": row["review_status"],
                "tier": row["tier"],
                "local_image_path": row["local_image_path"],
                "source_channel": row["source_channel"],
                "scene_bucket": row["scene_bucket"],
                "image_record": json.loads(str(row["raw_json"])),
            }
        )

    path = Path(output_path)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(path), "records": len(queue), "dry_run": dry_run}


def apply_review_queue(
    db: EngineDB,
    decisions_path: str | Path,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    decisions = load_json_list(decisions_path)
    now = utcnow_iso()
    rows = []
    for decision in decisions:
        instance_id = str(decision.get("instance_id") or "").strip()
        if not instance_id:
            continue
        tier = str(decision.get("tier") or "proposal").strip().lower()
        review_status = str(decision.get("review_status") or "needs_review").strip().lower()
        rows.append(
            {
                "instance_id": instance_id,
                "tier": tier,
                "review_status": review_status,
                "updated_at": now,
            }
        )
    if not dry_run:
        db.apply_review_decisions(rows)
    return {"input": str(decisions_path), "applied": len(rows), "dry_run": dry_run}


def phase1_workflow(
    db: EngineDB,
    *,
    records_json: str | Path,
    brand_records_json: str | Path,
    review_output: str | Path,
    dry_run: bool = False,
    resume: bool = False,
    image_tier: str = "proposal",
    brand_tier: str = "silver",
    instance_tier: str = "proposal",
    segment_records_json: str | Path | None = None,
    segment_enrich: bool = True,
    clip_retrieval_model_id: str = "openai/clip-vit-base-patch32",
    caption_model_id: str = "Salesforce/blip-image-captioning-base",
    skip_detector: bool = False,
    skip_ocr: bool = False,
    skip_clip_retrieval: bool = False,
    skip_captioning: bool = False,
    use_vlm: bool = False,
    vlm_model_id: str = "llava-hf/llava-1.5-7b-hf",
    use_qwen_qa: bool = False,
    qwen_model_id: str = "Qwen/Qwen2.5-7B-Instruct",
) -> Dict[str, Any]:
    ontology_stats = seed_ontology_from_json(db, brand_records_json, tier=brand_tier, dry_run=dry_run)
    image_stats = ingest_image_records(
        db,
        load_json_list(records_json),
        tier=image_tier,
        dry_run=dry_run,
        resume=resume,
    )
    gate_stats = gate_images(
        db,
        dry_run=dry_run,
        resume=resume,
        report=True,
    )
    if segment_records_json:
        annotation_stats = annotate_from_segment_records(
            db,
            load_json_list(segment_records_json),
            tier=instance_tier,
            dry_run=dry_run,
            resume=resume,
            enrich=segment_enrich,
            brand_catalog=brand_catalog_from_db(db),
            clip_retrieval_model_id=clip_retrieval_model_id,
            caption_model_id=caption_model_id,
            skip_ocr=skip_ocr,
            skip_clip_retrieval=skip_clip_retrieval,
            skip_captioning=skip_captioning,
            use_vlm=use_vlm,
            vlm_model_id=vlm_model_id,
            use_qwen_qa=use_qwen_qa,
            qwen_model_id=qwen_model_id,
        )
    else:
        annotation_stats = annotate_db_proposals(
            db,
            tier=instance_tier,
            dry_run=dry_run,
            resume=resume,
            clip_retrieval_model_id=clip_retrieval_model_id,
            caption_model_id=caption_model_id,
            skip_detector=skip_detector,
            skip_ocr=skip_ocr,
            skip_clip_retrieval=skip_clip_retrieval,
            skip_captioning=skip_captioning,
            use_vlm=use_vlm,
            vlm_model_id=vlm_model_id,
            use_qwen_qa=use_qwen_qa,
            qwen_model_id=qwen_model_id,
        )
    review_stats = review_queue(db, review_output, dry_run=dry_run)
    return {
        "ontology": ontology_stats,
        "images": image_stats,
        "gate": gate_stats,
        "annotation": annotation_stats,
        "review": review_stats,
    }
