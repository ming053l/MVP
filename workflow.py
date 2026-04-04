from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import torch

from .annotator import annotate_db_proposals, brand_catalog_from_db
from .backends import (
    BackendProtocol,
    BLIPCaptionEngine,
    CLIPBrandRetriever,
    CLIPLogoQualityScorer,
    GroundingDINOProposalDetector,
    LLaMAVLMEngine,
    PaddleOCREngine,
    QwenKnowledgeEngine,
    YOLOWorldLogoPrescreener,
)
from .db import EngineDB
from .engine import annotate_from_segment_records, brand_rows_from_records, ingest_image_records, load_json_list
from .quality import evaluate_image_quality, gate_report
from .record_types import ImageQualityUpdateRow, ReviewDecisionRow
from .schema import utcnow_iso


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
    registry: List[tuple[str, bool, Callable[[], BackendProtocol], Dict[str, Any]]] = [
        (
            "grounding_dino",
            not skip_detector,
            lambda: GroundingDINOProposalDetector(model_id=grounding_model_id),
            {"model_id": grounding_model_id},
        ),
        (
            "paddleocr",
            not skip_ocr,
            lambda: PaddleOCREngine(lang="en"),
            {},
        ),
        (
            "clip_logo_gate",
            not skip_clip,
            lambda: CLIPLogoQualityScorer(),
            {},
        ),
        (
            "clip_retrieval",
            not skip_clip_retrieval,
            lambda: CLIPBrandRetriever(),
            {},
        ),
        (
            "blip_caption",
            not skip_captioning,
            lambda: BLIPCaptionEngine(),
            {},
        ),
        (
            "vlm",
            use_vlm,
            lambda: LLaMAVLMEngine(model_id=vlm_model_id),
            {"model_id": vlm_model_id},
        ),
        (
            "qwen_qa",
            use_qwen_qa,
            lambda: QwenKnowledgeEngine(model_id=qwen_model_id),
            {"model_id": qwen_model_id},
        ),
        (
            "yolo_prescreen",
            not skip_prescreen,
            lambda: YOLOWorldLogoPrescreener(conf_threshold=prescreen_threshold),
            {"threshold": prescreen_threshold},
        ),
    ]

    for name, enabled, factory, extras in registry:
        backend = factory() if enabled else None
        statuses[name] = {
            "enabled": enabled,
            "available": None if backend is None else backend.available,
            "error": ("disabled" if backend is None else backend.error),
            **extras,
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

    warnings = []
    for name, payload in list(statuses.items()):
        if not isinstance(payload, dict):
            continue
        if payload.get("enabled") and payload.get("available") is False:
            warnings.append(f"{name}: {payload.get('error') or 'unavailable'}")
    statuses["warnings"] = warnings
    statuses["ready"] = len(warnings) == 0

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
        with db.transaction():
            db.upsert_brand_records(brand_rows, commit=False)
    return {"inserted": len(brand_rows), "tier": tier, "dry_run": dry_run}


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
    updates: List[ImageQualityUpdateRow] = []
    evaluated = []
    for row in image_rows:
        record = json.loads(str(row["raw_json"]))
        result = evaluate_image_quality(
            image_id=str(row["image_id"]),
            record=record,
            image_path=row["local_image_path"],
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
        with db.transaction():
            db.update_image_quality(updates, commit=False)

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
    rows: List[ReviewDecisionRow] = []
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
        with db.transaction():
            db.apply_review_decisions(rows, commit=False)
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
