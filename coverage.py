from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple


def configured_pairs() -> List[Tuple[str, str]]:
    from multi_brand_fetcher import BRAND_SOURCES

    return sorted((str(brand), str(category)) for brand, category in BRAND_SOURCES.keys())


def _image_pair_stats(db_path: Path) -> Dict[Tuple[str, str], Dict[str, int]]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                COALESCE(brand_hint, 'unknown') AS brand,
                COALESCE(category, 'unknown') AS category,
                COUNT(*) AS total_images,
                SUM(CASE WHEN COALESCE(quality_status, 'pending') = 'passed' THEN 1 ELSE 0 END) AS passed_images,
                SUM(CASE WHEN COALESCE(quality_status, 'pending') = 'filtered' THEN 1 ELSE 0 END) AS filtered_images,
                SUM(CASE WHEN COALESCE(quality_status, 'pending') = 'error' THEN 1 ELSE 0 END) AS error_images
            FROM image_records
            GROUP BY COALESCE(brand_hint, 'unknown'), COALESCE(category, 'unknown')
            """
        ).fetchall()

    stats: Dict[Tuple[str, str], Dict[str, int]] = {}
    for row in rows:
        key = (str(row["brand"]), str(row["category"]))
        stats[key] = {
            "total_images": int(row["total_images"] or 0),
            "passed_images": int(row["passed_images"] or 0),
            "filtered_images": int(row["filtered_images"] or 0),
            "error_images": int(row["error_images"] or 0),
        }
    return stats


def _logo_pair_stats(db_path: Path) -> Dict[Tuple[str, str], Dict[str, int]]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                COALESCE(ir.brand_hint, 'unknown') AS brand,
                COALESCE(ir.category, 'unknown') AS category,
                li.review_status,
                li.review_bucket,
                li.verification_json
            FROM logo_instances li
            JOIN image_records ir ON ir.image_id = li.image_id
            """
        ).fetchall()

    stats: Dict[Tuple[str, str], Dict[str, int]] = {}
    for row in rows:
        key = (str(row["brand"]), str(row["category"]))
        pair_stats = stats.setdefault(
            key,
            {
                "logo_instances": 0,
                "auto_accept_instances": 0,
                "reviewed_accept_instances": 0,
                "needs_review_instances": 0,
                "rejected_instances": 0,
                "must_review_instances": 0,
                "spot_check_instances": 0,
                "verification_conflicts": 0,
            },
        )
        pair_stats["logo_instances"] += 1
        review_status = str(row["review_status"] or "needs_review")
        review_bucket = str(row["review_bucket"] or "must_review")
        pair_stats[f"{review_status}_instances"] = pair_stats.get(f"{review_status}_instances", 0) + 1
        pair_stats[f"{review_bucket}_instances"] = pair_stats.get(f"{review_bucket}_instances", 0) + 1
        try:
            verification = json.loads(str(row["verification_json"])) if row["verification_json"] else {}
        except json.JSONDecodeError:
            verification = {}
        if str(verification.get("overall_status") or "") == "conflict":
            pair_stats["verification_conflicts"] += 1
    return stats


def build_coverage_plan(
    db_path: str | Path,
    *,
    target_per_pair: int = 20,
    max_pairs: int = 50,
) -> Dict[str, Any]:
    db_path = Path(db_path)
    configured = set(configured_pairs())
    image_stats = _image_pair_stats(db_path)
    logo_stats = _logo_pair_stats(db_path)
    observed = set(image_stats.keys()) | set(logo_stats.keys())
    all_pairs = sorted(configured | observed)

    pair_rows: List[Dict[str, Any]] = []
    for brand, category in all_pairs:
        image_row = image_stats.get((brand, category), {})
        logo_row = logo_stats.get((brand, category), {})
        total_images = int(image_row.get("total_images", 0))
        passed_images = int(image_row.get("passed_images", 0))
        logo_instances = int(logo_row.get("logo_instances", 0))
        accepted_instances = int(logo_row.get("auto_accept_instances", 0)) + int(logo_row.get("reviewed_accept_instances", 0))
        needs_review_instances = int(logo_row.get("needs_review_instances", 0))
        rejected_instances = int(logo_row.get("rejected_instances", 0))
        must_review_instances = int(logo_row.get("must_review_instances", 0))
        spot_check_instances = int(logo_row.get("spot_check_instances", 0))
        verification_conflicts = int(logo_row.get("verification_conflicts", 0))
        coverage_gap = max(0, int(target_per_pair) - passed_images)
        reject_rate = round(rejected_instances / logo_instances, 4) if logo_instances else 0.0
        review_load = must_review_instances + spot_check_instances

        is_configured = (brand, category) in configured
        if passed_images == 0:
            action = "collect_more"
            note = "no passed images yet"
        elif reject_rate >= 0.5 and logo_instances >= 5:
            action = "fix_pipeline"
            note = "high reject rate suggests prompt/rule drift"
        elif verification_conflicts >= 3:
            action = "verify_knowledge"
            note = "multiple verification conflicts"
        elif coverage_gap > 0:
            action = "collect_more"
            note = "coverage below target"
        else:
            action = "healthy"
            note = "coverage target met"

        priority_score = (coverage_gap * 10) + (verification_conflicts * 5) + (review_load * 2)
        if action == "fix_pipeline":
            priority_score += 25
        if action == "verify_knowledge":
            priority_score += 10

        pair_rows.append(
            {
                "brand": brand,
                "category": category,
                "configured_pair": is_configured,
                "total_images": total_images,
                "passed_images": passed_images,
                "logo_instances": logo_instances,
                "accepted_instances": accepted_instances,
                "needs_review_instances": needs_review_instances,
                "rejected_instances": rejected_instances,
                "must_review_instances": must_review_instances,
                "spot_check_instances": spot_check_instances,
                "verification_conflicts": verification_conflicts,
                "coverage_gap": coverage_gap,
                "reject_rate": reject_rate,
                "action": action,
                "priority_score": priority_score,
                "note": note,
            }
        )

    recommendations = sorted(
        [row for row in pair_rows if row["action"] != "healthy"],
        key=lambda row: (-int(row["priority_score"]), row["brand"], row["category"]),
    )[: int(max_pairs)]

    covered_pairs = sum(1 for row in pair_rows if row["passed_images"] > 0)
    healthy_pairs = sum(1 for row in pair_rows if row["action"] == "healthy")

    return {
        "db": str(db_path),
        "target_per_pair": int(target_per_pair),
        "totals": {
            "configured_pairs": len(configured),
            "observed_pairs": len(observed),
            "tracked_pairs": len(all_pairs),
            "covered_pairs": covered_pairs,
            "uncovered_pairs": max(0, len(all_pairs) - covered_pairs),
            "healthy_pairs": healthy_pairs,
            "pairs_needing_attention": len(recommendations),
        },
        "recommendations": recommendations,
        "pair_stats": pair_rows,
    }


def render_coverage_plan_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Coverage Plan",
        "",
        f"DB: `{summary['db']}`",
        "",
        "## Snapshot",
        "",
        f"- Configured pairs: {summary['totals']['configured_pairs']}",
        f"- Observed pairs: {summary['totals']['observed_pairs']}",
        f"- Tracked pairs: {summary['totals']['tracked_pairs']}",
        f"- Covered pairs: {summary['totals']['covered_pairs']}",
        f"- Uncovered pairs: {summary['totals']['uncovered_pairs']}",
        f"- Healthy pairs: {summary['totals']['healthy_pairs']}",
        f"- Pairs needing attention: {summary['totals']['pairs_needing_attention']}",
        f"- Target per pair: {summary['target_per_pair']}",
        "",
        "## Top Recommendations",
        "",
        "| Brand | Category | Scope | Passed | Instances | Reject Rate | Conflicts | Action | Note |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in summary["recommendations"]:
        lines.append(
            f"| {row['brand']} | {row['category']} | {'configured' if row['configured_pair'] else 'observed'} | "
            f"{row['passed_images']} | {row['logo_instances']} | "
            f"{row['reject_rate']:.2f} | {row['verification_conflicts']} | {row['action']} | {row['note']} |"
        )
    if not summary["recommendations"]:
        lines.append("| _none_ |  |  |  |  |  |  | healthy | all tracked pairs meet the current target |")
    lines.extend(
        [
            "",
            "## Planner Logic",
            "",
            "- `collect_more`: passed image coverage is below target",
            "- `verify_knowledge`: verification conflicts are accumulating",
            "- `fix_pipeline`: reject rate is too high, likely a prompt/rule issue",
            "- `healthy`: pair already meets the current target",
            "",
        ]
    )
    return "\n".join(lines)


def write_coverage_plan(
    db_path: str | Path,
    output_md: str | Path,
    output_json: str | Path,
    *,
    target_per_pair: int = 20,
    max_pairs: int = 50,
) -> Dict[str, Any]:
    summary = build_coverage_plan(db_path, target_per_pair=target_per_pair, max_pairs=max_pairs)
    md_path = Path(output_md)
    json_path = Path(output_json)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_coverage_plan_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
