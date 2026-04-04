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
