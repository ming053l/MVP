from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import EngineDB
from .batch import configured_pair_count, default_limit_per_pair, load_records, rebalance_records, save_records
from .engine import (
    annotate_from_segment_records,
    brand_rows_from_records,
    export_joined_records,
    import_run,
    ingest_image_records,
    load_json_list,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Logo data engine CLI.")
    parser.add_argument("--db", required=True, help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the SQLite schema")

    collect = subparsers.add_parser("collector-fetch-products", help="Run the product collector")
    collect_target = collect.add_mutually_exclusive_group(required=True)
    collect_target.add_argument("--all", action="store_true", help="Fetch all configured brand/category pairs")
    collect_target.add_argument("--brands", help="Comma-separated brand keys")
    collect.add_argument("--categories", help="Comma-separated category keys when --brands is used")
    collect.add_argument("--limit", type=int, default=4, help="Max records per pair")
    collect.add_argument("--output", required=True, help="Output records JSON path")
    collect.add_argument("--image-dir", required=True, help="Output image directory")
    collect.add_argument("--dry-run", action="store_true")

    collect_external = subparsers.add_parser("collector-prepare-external", help="Build external-source records from a local image collection")
    collect_external.add_argument("--collection-root", required=True, help="Root directory containing external images")
    collect_external.add_argument("--output", required=True, help="Output records JSON path")
    collect_external.add_argument("--metadata-csv", default=None, help="Optional CSV metadata file")
    collect_external.add_argument("--default-source", default=None, help="Fallback source name")
    collect_external.add_argument("--default-source-channel", default=None, help="Fallback source channel")
    collect_external.add_argument("--default-license", default="unknown", help="Fallback license label")
    collect_external.add_argument("--dry-run", action="store_true")

    collect_manifest = subparsers.add_parser("collector-ingest-manifest", help="Normalize one or more external manifests into shared records")
    collect_manifest.add_argument("--manifest", action="append", required=True, help="Manifest path; repeat for multiple files")
    collect_manifest.add_argument("--output", required=True, help="Output records JSON path")
    collect_manifest.add_argument("--image-dir", required=True, help="Output image directory for downloaded files")
    collect_manifest.add_argument("--default-license", default="unknown", help="Fallback license label")
    collect_manifest.add_argument("--dry-run", action="store_true")

    ontology_fetch = subparsers.add_parser("ontology-fetch-brands", help="Fetch brand ontology records from product records")
    ontology_fetch.add_argument("--product-records", required=True, help="Input product records JSON")
    ontology_fetch.add_argument("--output", required=True, help="Output brand_records JSON")
    ontology_fetch.add_argument("--dry-run", action="store_true")

    seed = subparsers.add_parser("seed-ontology", help="Import brand ontology records")
    seed.add_argument("--brand-records", required=True, help="Path to brand_records.json")
    seed.add_argument("--tier", default="silver", help="Tier for imported brand rows")
    seed.add_argument("--dry-run", action="store_true")

    ingest = subparsers.add_parser("ingest-images", help="Import image records into the engine")
    ingest.add_argument("--records-json", required=True, help="Path to image records JSON")
    ingest.add_argument("--tier", default="proposal", help="Tier for image records")
    ingest.add_argument("--resume", action="store_true", help="Skip records already present in DB")
    ingest.add_argument("--dry-run", action="store_true")

    annotate = subparsers.add_parser("annotate-proposals", help="Import proposal/logo-instance rows from segment records")
    annotate.add_argument("--records-json", required=True, help="Path to segment records JSON")
    annotate.add_argument("--tier", default="proposal", help="Tier for logo instances")
    annotate.add_argument("--resume", action="store_true", help="Skip instances already present in DB")
    annotate.add_argument("--dry-run", action="store_true")

    annotate_db = subparsers.add_parser("annotate-db", help="Run detector + PaddleOCR over image_records in DB")
    annotate_db.add_argument("--limit", type=int, default=None, help="Optional cap on images to process")
    annotate_db.add_argument("--source-channel", default=None, help="Optional source_channel filter")
    annotate_db.add_argument("--tier", default="proposal", help="Tier for created logo instances")
    annotate_db.add_argument("--resume", action="store_true", help="Skip instances already present in DB")
    annotate_db.add_argument("--allow-filtered", action="store_true", help="Also annotate images filtered by quality gate")
    annotate_db.add_argument("--skip-detector", action="store_true", help="Disable GroundingDINO proposal detection")
    annotate_db.add_argument("--skip-ocr", action="store_true", help="Disable OCR enrichment")
    annotate_db.add_argument("--skip-clip-retrieval", action="store_true", help="Disable CLIP brand retrieval attribution")
    annotate_db.add_argument("--skip-captioning", action="store_true", help="Disable BLIP captioning enrichment")
    annotate_db.add_argument("--clip-retrieval-model-id", default="openai/clip-vit-base-patch32", help="CLIP model for brand retrieval")
    annotate_db.add_argument("--caption-model-id", default="Salesforce/blip-image-captioning-base", help="Caption model for high-quality images")
    annotate_db.add_argument("--use-vlm", action="store_true", help="Enable LLaMA-style VLM caption/QA backend")
    annotate_db.add_argument("--vlm-model-id", default="llava-hf/llava-1.5-7b-hf", help="VLM model id (e.g., LLaVA)")
    annotate_db.add_argument("--use-qwen-qa", action="store_true", help="Enable Qwen knowledge QA enrichment")
    annotate_db.add_argument("--qwen-model-id", default="Qwen/Qwen2.5-7B-Instruct", help="Qwen model id")
    annotate_db.add_argument("--dry-run", action="store_true")

    gate = subparsers.add_parser("gate", help="Run quality gates over image_records before annotation")
    gate.add_argument("--all", action="store_true", help="Process all matching image_records")
    gate.add_argument("--limit", type=int, default=None, help="Optional cap on images to process")
    gate.add_argument("--source-channel", default=None, help="Optional source_channel filter")
    gate.add_argument("--resume", action="store_true", help="Skip images that already have a gate decision")
    gate.add_argument("--report", action="store_true", help="Include per-gate survival statistics in the output")
    gate.add_argument("--min-width", type=int, default=256, help="Minimum image width")
    gate.add_argument("--min-height", type=int, default=256, help="Minimum image height")
    gate.add_argument("--blur-threshold", type=float, default=45.0, help="Minimum Laplacian variance")
    gate.add_argument("--clip-threshold", type=float, default=0.22, help="Minimum CLIP logo prompt score")
    gate.add_argument("--clip-soft-floor", type=float, default=0.08, help="Soft floor for trusted catalog images before hard filtering")
    gate.add_argument("--phash-distance-threshold", type=int, default=6, help="Maximum near-duplicate pHash distance")
    gate.add_argument("--prescreen-threshold", type=float, default=0.3, help="YOLO prescreen confidence threshold")
    gate.add_argument("--skip-clip", action="store_true", help="Disable the CLIP logo relevance gate")
    gate.add_argument("--skip-prescreen", action="store_true", help="Disable the YOLO logo prescreen gate")
    gate.add_argument("--dry-run", action="store_true")

    review = subparsers.add_parser("review-queue", help="Export a review queue from logo_instances")
    review.add_argument("--output", required=True, help="Output JSON path")
    review.add_argument("--limit", type=int, default=200, help="Max queue size")
    review.add_argument("--dry-run", action="store_true")

    review_apply = subparsers.add_parser("review-apply", help="Apply reviewed tier/review_status decisions back into the DB")
    review_apply.add_argument("--decisions-json", required=True, help="Input JSON list with instance_id/tier/review_status")
    review_apply.add_argument("--dry-run", action="store_true")

    phase1 = subparsers.add_parser("phase1-workflow", help="Run ontology -> ingest -> annotate -> review on JSON inputs")
    phase1.add_argument("--records-json", required=True, help="Input image records JSON")
    phase1.add_argument("--brand-records", required=True, help="Input brand_records JSON")
    phase1.add_argument("--review-output", required=True, help="Output review queue JSON")
    phase1.add_argument("--segment-records", default=None, help="Optional SAM3 segment records JSON")
    phase1.add_argument("--segment-enrich", action="store_true", help="Enrich SAM3 segments with OCR/CLIP/BLIP")
    phase1.add_argument("--skip-detector", action="store_true", help="Disable GroundingDINO proposal detection")
    phase1.add_argument("--skip-ocr", action="store_true", help="Disable OCR enrichment")
    phase1.add_argument("--skip-clip-retrieval", action="store_true", help="Disable CLIP brand retrieval attribution")
    phase1.add_argument("--skip-captioning", action="store_true", help="Disable BLIP captioning enrichment")
    phase1.add_argument("--clip-retrieval-model-id", default="openai/clip-vit-base-patch32", help="CLIP model for brand retrieval")
    phase1.add_argument("--caption-model-id", default="Salesforce/blip-image-captioning-base", help="Caption model for high-quality images")
    phase1.add_argument("--use-vlm", action="store_true", help="Enable LLaMA-style VLM caption/QA backend")
    phase1.add_argument("--vlm-model-id", default="llava-hf/llava-1.5-7b-hf", help="VLM model id (e.g., LLaVA)")
    phase1.add_argument("--use-qwen-qa", action="store_true", help="Enable Qwen knowledge QA enrichment")
    phase1.add_argument("--qwen-model-id", default="Qwen/Qwen2.5-7B-Instruct", help="Qwen model id")
    phase1.add_argument("--resume", action="store_true")
    phase1.add_argument("--dry-run", action="store_true")

    balance = subparsers.add_parser("balance-records", help="Rebalance a collected record set down to a target size")
    balance.add_argument("--input", required=True, help="Input records JSON")
    balance.add_argument("--output", required=True, help="Output balanced records JSON")
    balance.add_argument("--target", required=True, type=int, help="Target number of records")

    analyze = subparsers.add_parser("analyze-run", help="Generate analysis markdown/json for an engine run directory")
    analyze.add_argument("--run-dir", required=True, help="Run directory produced by run_pipeline or batch runner")
    analyze.add_argument("--output-md", required=True, help="Output analysis markdown path")
    analyze.add_argument("--output-json", required=True, help="Output machine-readable summary json path")
    analyze.add_argument("--target-records", type=int, default=None, help="Optional target used for the batch")

    import_run_parser = subparsers.add_parser("import-run", help="Import a completed run directory into the engine")
    import_run_parser.add_argument("--run-dir", required=True, help="Path to runs/<run_name>")
    import_run_parser.add_argument("--resume", action="store_true", help="Skip rows already present in DB")
    import_run_parser.add_argument("--dry-run", action="store_true")

    export = subparsers.add_parser("export-kb", help="Export joined image/logo/brand records")
    export.add_argument("--output", required=True, help="Output JSON path")
    export.add_argument("--dry-run", action="store_true")

    segment = subparsers.add_parser("segment-sam3", help="Run SAM3 logo segmentation over records JSON")
    segment.add_argument("--input-records", required=True, help="Input records JSON")
    segment.add_argument("--output", required=True, help="Output segment records JSON")
    segment.add_argument("--mask-dir", required=True, help="Output mask directory")
    segment.add_argument("--viz-dir", required=True, help="Output visualization directory")
    segment.add_argument("--brand-records", default=None, help="Optional brand_records JSON")
    segment.add_argument("--checkpoint-path", default=None, help="Optional SAM3 checkpoint path")
    segment.add_argument("--device", default=None, help="SAM3 device override")
    segment.add_argument("--max-records", type=int, default=None, help="Optional record cap")
    segment.add_argument(
        "--object-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run GroundingDINO object-first before logo detection (default: true)",
    )
    segment.add_argument("--dry-run", action="store_true")

    preflight = subparsers.add_parser("preflight", help="Check model availability for the pipeline")
    preflight.add_argument("--with-sam3", action="store_true", help="Check SAM3 availability")
    preflight.add_argument("--sam3-checkpoint", default=None, help="Optional SAM3 checkpoint path")
    preflight.add_argument("--sam3-device", default=None, help="SAM3 device override")
    preflight.add_argument(
        "--object-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Check object-first GroundingDINO (default: true)",
    )
    preflight.add_argument("--use-vlm", action="store_true", help="Enable VLM availability check")
    preflight.add_argument("--vlm-model-id", default="llava-hf/llava-1.5-7b-hf", help="VLM model id")
    preflight.add_argument("--use-qwen-qa", action="store_true", help="Enable Qwen QA availability check")
    preflight.add_argument("--qwen-model-id", default="Qwen/Qwen2.5-7B-Instruct", help="Qwen model id")
    preflight.add_argument("--skip-detector", action="store_true", help="Disable GroundingDINO proposal detection")
    preflight.add_argument("--skip-ocr", action="store_true", help="Disable OCR check")
    preflight.add_argument("--skip-clip", action="store_true", help="Disable CLIP logo gate check")
    preflight.add_argument("--skip-clip-retrieval", action="store_true", help="Disable CLIP brand retrieval check")
    preflight.add_argument("--skip-captioning", action="store_true", help="Disable BLIP captioning check")
    preflight.add_argument("--skip-prescreen", action="store_true", help="Disable YOLO prescreen check")
    preflight.add_argument("--prescreen-threshold", type=float, default=0.3, help="YOLO prescreen threshold")

    export_records = subparsers.add_parser("export-image-records", help="Export raw image_records from the DB")
    export_records.add_argument("--output", required=True, help="Output JSON path")
    export_records.add_argument("--quality-status", default=None, help="Optional image quality_status filter")
    export_records.add_argument("--limit", type=int, default=None, help="Optional row limit")
    export_records.add_argument("--dry-run", action="store_true")

    summary = subparsers.add_parser("summary", help="Print table counts")
    summary.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    batch_plan = subparsers.add_parser("batch-plan", help="Compute the recommended per-pair fetch limit for a target batch size")
    batch_plan.add_argument("--target", type=int, required=True, help="Target number of records")
    batch_plan.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)

    with EngineDB(db_path) as db:
        db.init_schema()

        if args.command == "init-db":
            result = {"db": str(db_path), "status": "initialized"}

        elif args.command == "collector-fetch-products":
            from .workflow import collector_fetch_products

            result = collector_fetch_products(
                output_path=args.output,
                image_dir=args.image_dir,
                all_pairs=args.all,
                brands=args.brands,
                categories=args.categories,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            result.update({"db": str(db_path)})

        elif args.command == "collector-prepare-external":
            from .workflow import collector_prepare_external_records

            result = collector_prepare_external_records(
                collection_root=args.collection_root,
                output_path=args.output,
                metadata_csv=args.metadata_csv,
                default_source=args.default_source,
                default_source_channel=args.default_source_channel,
                default_license=args.default_license,
                dry_run=args.dry_run,
            )
            result.update({"db": str(db_path)})

        elif args.command == "collector-ingest-manifest":
            from .workflow import collector_ingest_external_manifests

            result = collector_ingest_external_manifests(
                manifests=args.manifest,
                output_path=args.output,
                image_dir=args.image_dir,
                default_license=args.default_license,
                dry_run=args.dry_run,
            )
            result.update({"db": str(db_path)})

        elif args.command == "ontology-fetch-brands":
            from .workflow import ontology_fetch_brand_records

            result = ontology_fetch_brand_records(
                product_records_path=args.product_records,
                output_path=args.output,
                dry_run=args.dry_run,
            )
            result.update({"db": str(db_path)})

        elif args.command == "seed-ontology":
            from .workflow import seed_ontology_from_json

            result = seed_ontology_from_json(db, args.brand_records, tier=args.tier, dry_run=args.dry_run)
            result.update({"db": str(db_path)})

        elif args.command == "ingest-images":
            stats = ingest_image_records(
                db,
                load_json_list(args.records_json),
                tier=args.tier,
                dry_run=args.dry_run,
                resume=args.resume,
            )
            result = {"db": str(db_path), "stats": stats, "dry_run": args.dry_run, "resume": args.resume}

        elif args.command == "annotate-proposals":
            records = load_json_list(args.records_json)
            stats = annotate_from_segment_records(
                db,
                records,
                tier=args.tier,
                dry_run=args.dry_run,
                resume=args.resume,
            )
            result = {"db": str(db_path), "stats": stats, "dry_run": args.dry_run, "resume": args.resume}

        elif args.command == "annotate-db":
            from .workflow import annotate_db_proposals

            stats = annotate_db_proposals(
                db,
                limit=args.limit,
                source_channel=args.source_channel,
                tier=args.tier,
                dry_run=args.dry_run,
                resume=args.resume,
                allow_filtered=args.allow_filtered,
                skip_detector=args.skip_detector,
                skip_ocr=args.skip_ocr,
                skip_clip_retrieval=args.skip_clip_retrieval,
                skip_captioning=args.skip_captioning,
                clip_retrieval_model_id=args.clip_retrieval_model_id,
                caption_model_id=args.caption_model_id,
                use_vlm=args.use_vlm,
                vlm_model_id=args.vlm_model_id,
                use_qwen_qa=args.use_qwen_qa,
                qwen_model_id=args.qwen_model_id,
            )
            result = {"db": str(db_path), "stats": stats, "dry_run": args.dry_run, "resume": args.resume}

        elif args.command == "gate":
            from .workflow import gate_images

            stats = gate_images(
                db,
                limit=args.limit,
                source_channel=args.source_channel,
                dry_run=args.dry_run,
                resume=args.resume,
                report=args.report,
                min_width=args.min_width,
                min_height=args.min_height,
                blur_threshold=args.blur_threshold,
                clip_threshold=args.clip_threshold,
                clip_soft_floor=args.clip_soft_floor,
                phash_distance_threshold=args.phash_distance_threshold,
                skip_clip=args.skip_clip,
                skip_prescreen=args.skip_prescreen,
                prescreen_threshold=args.prescreen_threshold,
            )
            result = {"db": str(db_path), "stats": stats, "dry_run": args.dry_run, "resume": args.resume}

        elif args.command == "review-queue":
            from .workflow import review_queue

            result = review_queue(db, output_path=args.output, limit=args.limit, dry_run=args.dry_run)
            result.update({"db": str(db_path)})

        elif args.command == "review-apply":
            from .workflow import apply_review_queue

            result = apply_review_queue(db, decisions_path=args.decisions_json, dry_run=args.dry_run)
            result.update({"db": str(db_path)})

        elif args.command == "phase1-workflow":
            from .workflow import phase1_workflow

            result = phase1_workflow(
                db,
                records_json=args.records_json,
                brand_records_json=args.brand_records,
                review_output=args.review_output,
                dry_run=args.dry_run,
                resume=args.resume,
                segment_records_json=args.segment_records,
                segment_enrich=args.segment_enrich,
                clip_retrieval_model_id=args.clip_retrieval_model_id,
                caption_model_id=args.caption_model_id,
                skip_detector=args.skip_detector,
                skip_ocr=args.skip_ocr,
                skip_clip_retrieval=args.skip_clip_retrieval,
                skip_captioning=args.skip_captioning,
                use_vlm=args.use_vlm,
                vlm_model_id=args.vlm_model_id,
                use_qwen_qa=args.use_qwen_qa,
                qwen_model_id=args.qwen_model_id,
            )
            result.update({"db": str(db_path), "dry_run": args.dry_run, "resume": args.resume})

        elif args.command == "balance-records":
            records = load_records(args.input)
            balanced = rebalance_records(records, target_records=args.target)
            save_records(args.output, balanced)
            result = {
                "input": args.input,
                "output": args.output,
                "seen": len(records),
                "selected": len(balanced),
                "target": args.target,
            }

        elif args.command == "analyze-run":
            from .reporting import write_run_analysis

            summary_payload = write_run_analysis(
                args.run_dir,
                args.output_md,
                args.output_json,
                target_records=args.target_records,
            )
            result = {
                "run_dir": args.run_dir,
                "output_md": args.output_md,
                "output_json": args.output_json,
                "target_records": args.target_records,
                "summary": summary_payload["totals"],
            }

        elif args.command == "import-run":
            result = import_run(
                db,
                run_dir=args.run_dir,
                dry_run=args.dry_run,
                resume=args.resume,
            )
            result.update({"db": str(db_path), "run_dir": args.run_dir, "dry_run": args.dry_run, "resume": args.resume})

        elif args.command == "export-kb":
            result = export_joined_records(db, output_path=args.output, dry_run=args.dry_run)
            result.update({"db": str(db_path), "dry_run": args.dry_run})

        elif args.command == "segment-sam3":
            from .workflow import segment_with_sam3

            result = segment_with_sam3(
                input_records=args.input_records,
                output_records=args.output,
                mask_dir=args.mask_dir,
                viz_dir=args.viz_dir,
                brand_records=args.brand_records,
                checkpoint_path=args.checkpoint_path,
                device=args.device,
                max_records=args.max_records,
                object_first=args.object_first,
                dry_run=args.dry_run,
            )
            result.update({"db": str(db_path)})

        elif args.command == "preflight":
            from .workflow import preflight_models

            result = preflight_models(
                with_sam3=args.with_sam3,
                sam3_checkpoint=args.sam3_checkpoint,
                sam3_device=args.sam3_device,
                object_first=args.object_first,
                use_vlm=args.use_vlm,
                vlm_model_id=args.vlm_model_id,
                use_qwen_qa=args.use_qwen_qa,
                qwen_model_id=args.qwen_model_id,
                skip_detector=args.skip_detector,
                skip_ocr=args.skip_ocr,
                skip_clip=args.skip_clip,
                skip_clip_retrieval=args.skip_clip_retrieval,
                skip_captioning=args.skip_captioning,
                skip_prescreen=args.skip_prescreen,
                prescreen_threshold=args.prescreen_threshold,
            )
            result.update({"db": str(db_path)})

        elif args.command == "export-image-records":
            rows = db.export_image_records(quality_status=args.quality_status, limit=args.limit)
            path = Path(args.output)
            if not args.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            result = {
                "db": str(db_path),
                "output": str(path),
                "records": len(rows),
                "quality_status": args.quality_status,
                "dry_run": args.dry_run,
            }

        elif args.command == "summary":
            result = {"db": str(db_path), "counts": db.table_counts()}

        elif args.command == "batch-plan":
            result = {
                "target": args.target,
                "configured_pairs": configured_pair_count(),
                "recommended_limit_per_pair": default_limit_per_pair(args.target),
            }

        else:  # pragma: no cover
            print(f"[error] unknown command: {args.command}", file=sys.stderr)
            return 2

    if getattr(args, "pretty", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
