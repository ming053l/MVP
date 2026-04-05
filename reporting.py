from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def top_items(counter: Counter, limit: int = 50) -> List[Dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(limit)]


def render_table(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"### {title}\n\n_No data_\n"
    lines = [
        f"### {title}",
        "",
        "| Value | Count |",
        "| --- | ---: |",
    ]
    for row in rows:
        lines.append(f"| {row['value']} | {row['count']} |")
    lines.append("")
    return "\n".join(lines)


def _db_counter(db_path: Path, query: str) -> Counter:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
    return Counter({str(row[0]): int(row[1]) for row in rows})


def _gate_reason_counter(db_path: Path) -> Counter:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT quality_gate_json
            FROM image_records
            WHERE quality_gate_json IS NOT NULL AND quality_gate_json != ''
            """
        ).fetchall()
    counter: Counter = Counter()
    for row in rows:
        try:
            payload = json.loads(str(row["quality_gate_json"]))
        except json.JSONDecodeError:
            continue
        reason = payload.get("failure_reason")
        if reason:
            counter[str(reason)] += 1
    return counter


def build_run_analysis(run_dir: str | Path, target_records: int | None = None) -> Dict[str, Any]:
    run_path = Path(run_dir)
    fetch_records = load_json(run_path / "fetch" / "records.json")
    brand_records = load_json(run_path / "brand" / "brand_records.json")
    knowledge_base = load_json(run_path / "export" / "knowledge_base.json")
    db_path = run_path / "engine" / "logo_engine.db"

    if not isinstance(fetch_records, list):
        raise TypeError("fetch/records.json must be a list")
    if not isinstance(brand_records, list):
        raise TypeError("brand/brand_records.json must be a list")
    if not isinstance(knowledge_base, list):
        raise TypeError("export/knowledge_base.json must be a list")

    brand_counter = Counter(str(rec.get("brand") or "unknown") for rec in fetch_records)
    category_counter = Counter(str(rec.get("category") or "unknown") for rec in fetch_records)
    source_counter = Counter(str(rec.get("source") or "unknown") for rec in fetch_records)
    source_channel_counter = Counter(str(rec.get("source_channel") or "unknown") for rec in fetch_records)
    source_kind_counter = Counter(str(rec.get("source_kind") or "unknown") for rec in fetch_records)
    pair_counter = Counter(f"{rec.get('brand')} / {rec.get('category')}" for rec in fetch_records)

    quality_counter = _db_counter(
        db_path,
        """
        SELECT COALESCE(quality_status, 'pending') AS quality_status, COUNT(*)
        FROM image_records
        GROUP BY COALESCE(quality_status, 'pending')
        ORDER BY quality_status
        """,
    )
    review_counter = _db_counter(
        db_path,
        """
        SELECT COALESCE(review_status, 'missing') AS review_status, COUNT(*)
        FROM logo_instances
        GROUP BY COALESCE(review_status, 'missing')
        ORDER BY review_status
        """,
    )
    tier_counter = _db_counter(
        db_path,
        """
        SELECT COALESCE(tier, 'missing') AS tier, COUNT(*)
        FROM logo_instances
        GROUP BY COALESCE(tier, 'missing')
        ORDER BY tier
        """,
    )
    gate_reason_counter = _gate_reason_counter(db_path)

    matched_brands = sum(1 for row in brand_records if row.get("matched"))
    quality_passed = quality_counter.get("passed", 0)
    quality_filtered = quality_counter.get("filtered", 0)
    logo_instances = sum(review_counter.values())

    return {
        "run_dir": str(run_path),
        "target_records": target_records,
        "totals": {
            "fetched_records": len(fetch_records),
            "matched_brands": matched_brands,
            "knowledge_base_records": len(knowledge_base),
            "unique_brands": len(brand_counter),
            "unique_categories": len(category_counter),
            "unique_sources": len(source_counter),
            "quality_passed": quality_passed,
            "quality_filtered": quality_filtered,
            "logo_instances": logo_instances,
        },
        "target_achieved": target_records is None or len(fetch_records) >= target_records,
        "distributions": {
            "pairs": top_items(pair_counter),
            "brands": top_items(brand_counter),
            "categories": top_items(category_counter),
            "sources": top_items(source_counter),
            "source_channels": top_items(source_channel_counter),
            "source_kinds": top_items(source_kind_counter),
            "quality_status": top_items(quality_counter),
            "gate_failure_reasons": top_items(gate_reason_counter),
            "review_status": top_items(review_counter),
            "logo_instance_tiers": top_items(tier_counter),
        },
    }


def render_run_analysis_markdown(summary: Dict[str, Any]) -> str:
    totals = summary["totals"]
    distributions = summary["distributions"]
    target_line = (
        f"- Target records: {summary['target_records']}\n- Target achieved: {summary['target_achieved']}"
        if summary.get("target_records") is not None
        else ""
    )
    return f"""# Batch Run Analysis

Run directory: `{summary['run_dir']}`

## Snapshot

- Fetched records: {totals['fetched_records']}
- Matched brands: {totals['matched_brands']}
- Knowledge-base records: {totals['knowledge_base_records']}
- Unique brands: {totals['unique_brands']}
- Unique categories: {totals['unique_categories']}
- Unique sources: {totals['unique_sources']}
- Quality passed: {totals['quality_passed']}
- Quality filtered: {totals['quality_filtered']}
- Logo instances: {totals['logo_instances']}
{target_line}

## Workflow

```mermaid
flowchart LR
    A[collector-fetch-products --all] --> B[meta/raw_records.json]
    B --> C[balance-records target sampler]
    C --> D[fetch/records.json]
    D --> E[ontology-fetch-brands]
    D --> F[phase1-workflow]
    E --> F
    F --> G[Quality Gate]
    G --> H[annotate-db]
    H --> I[review/review_queue.json]
    F --> J[export/knowledge_base.json]
    J --> K[analysis/analysis.md]
```

## Notes

This batch runner intentionally oversamples each configured brand/category pair first, then rebalances down to the requested target. That keeps the final set more evenly spread across brand, category, source, and source_channel than a simple first-N truncation.

The quality gate sits before annotation, so the review queue and proposal stage only spend time on images that survive the early filters.

{render_table("Brand / Category Pairs", distributions['pairs'])}
{render_table("Brands", distributions['brands'])}
{render_table("Categories", distributions['categories'])}
{render_table("Sources", distributions['sources'])}
{render_table("Source Channels", distributions['source_channels'])}
{render_table("Source Kinds", distributions['source_kinds'])}
{render_table("Quality Status", distributions['quality_status'])}
{render_table("Gate Failure Reasons", distributions['gate_failure_reasons'])}
{render_table("Review Status", distributions['review_status'])}
{render_table("Logo Instance Tiers", distributions['logo_instance_tiers'])}
"""


def write_run_analysis(
    run_dir: str | Path,
    output_md: str | Path,
    output_json: str | Path,
    target_records: int | None = None,
) -> Dict[str, Any]:
    summary = build_run_analysis(run_dir, target_records=target_records)
    md_path = Path(output_md)
    json_path = Path(output_json)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_run_analysis_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def build_stage_metrics_report(db_path: str | Path, *, limit: int = 100) -> Dict[str, Any]:
    db_path = Path(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT metric_id, run_id, stage_name, command_name, metrics_json, created_at
            FROM stage_metrics
            ORDER BY metric_id DESC
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()

    entries: List[Dict[str, Any]] = []
    latest_by_stage: Dict[str, Dict[str, Any]] = {}
    stage_counts: Counter = Counter()
    for row in rows:
        payload = json.loads(str(row["metrics_json"]))
        entry = {
            "metric_id": int(row["metric_id"]),
            "run_id": str(row["run_id"]),
            "stage_name": str(row["stage_name"]),
            "command_name": row["command_name"],
            "created_at": str(row["created_at"]),
            "metrics": payload,
        }
        entries.append(entry)
        stage_counts[entry["stage_name"]] += 1
        if entry["stage_name"] not in latest_by_stage:
            latest_by_stage[entry["stage_name"]] = entry

    recommendations: List[str] = []
    gate = latest_by_stage.get("gate", {}).get("metrics", {})
    gate_seen = int(gate.get("seen_images") or 0)
    gate_passed = int((gate.get("status_counts") or {}).get("passed") or 0)
    if gate_seen and gate_passed / gate_seen < 0.4:
        recommendations.append("Quality gate pass rate is below 40%; inspect collectors or loosen acquisition sources.")

    annotation = latest_by_stage.get("annotate_db", {}).get("metrics", {})
    if int(annotation.get("verification_conflicts") or 0) > 0:
        recommendations.append("Verification conflicts were detected; review Qwen enrichment or ontology mappings.")
    if int(annotation.get("text_only_instances") or 0) > 0:
        recommendations.append("Text-only proposals are being created; this is expected in Phase 1 lite, but visual enrichment is still pending.")

    review = latest_by_stage.get("review_queue", {}).get("metrics", {})
    must_review = int((review.get("selected_bucket_counts") or {}).get("must_review") or 0)
    spot_check = int((review.get("selected_bucket_counts") or {}).get("spot_check") or 0)
    if must_review > 0:
        recommendations.append(f"Review queue still has {must_review} must-review items; this is the main human-load driver.")
    if spot_check > 0:
        recommendations.append(f"Spot-check queue currently samples {spot_check} records; use this to recalibrate acceptance thresholds.")

    return {
        "db": str(db_path),
        "limit": int(limit),
        "totals": {
            "metric_rows": len(entries),
            "unique_stages": len(stage_counts),
        },
        "latest_by_stage": latest_by_stage,
        "stage_counts": dict(stage_counts),
        "recommendations": recommendations,
        "recent_entries": entries,
    }


def render_stage_metrics_markdown(summary: Dict[str, Any]) -> str:
    latest_rows = summary["latest_by_stage"]
    lines = [
        "# Stage Metrics Report",
        "",
        f"DB: `{summary['db']}`",
        "",
        "## Snapshot",
        "",
        f"- Metric rows loaded: {summary['totals']['metric_rows']}",
        f"- Unique stages: {summary['totals']['unique_stages']}",
        "",
        "## Latest Stage Rows",
        "",
        "| Stage | Created At | Command | Highlights |",
        "| --- | --- | --- | --- |",
    ]
    for stage_name in sorted(latest_rows):
        row = latest_rows[stage_name]
        metrics = row["metrics"]
        highlights = []
        for key in ("seen_images", "updated_images", "inserted", "inserted_instances", "records"):
            if key in metrics:
                highlights.append(f"{key}={metrics[key]}")
        if "review_bucket_counts" in metrics:
            highlights.append(f"review_bucket_counts={metrics['review_bucket_counts']}")
        if "status_counts" in metrics:
            highlights.append(f"status_counts={metrics['status_counts']}")
        lines.append(
            f"| {stage_name} | {row['created_at']} | {row.get('command_name') or ''} | {'; '.join(highlights) or '_none_'} |"
        )
    lines.extend(["", "## Recommendations", ""])
    if summary["recommendations"]:
        for item in summary["recommendations"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No immediate issues detected from the latest stage metrics.")
    lines.extend(["", "## Stage Frequency", "", "| Stage | Count |", "| --- | ---: |"])
    for stage_name, count in sorted(summary["stage_counts"].items()):
        lines.append(f"| {stage_name} | {count} |")
    lines.append("")
    return "\n".join(lines)


def write_stage_metrics_report(
    db_path: str | Path,
    output_md: str | Path,
    output_json: str | Path,
    *,
    limit: int = 100,
) -> Dict[str, Any]:
    summary = build_stage_metrics_report(db_path, limit=limit)
    md_path = Path(output_md)
    json_path = Path(output_json)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_stage_metrics_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
