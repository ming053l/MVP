from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
from PIL import Image

from .backends import CLIPLogoQualityScorer, YOLOWorldLogoPrescreener
from .schema import json_text, utcnow_iso


DEFAULT_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "JPG"}


def phash_hamming_distance(left: str, right: str) -> int:
    value = int(left, 16) ^ int(right, 16)
    return bin(value).count("1")


def laplacian_variance(gray_pixels: np.ndarray) -> float:
    center = gray_pixels[1:-1, 1:-1]
    laplacian = (
        gray_pixels[:-2, 1:-1]
        + gray_pixels[2:, 1:-1]
        + gray_pixels[1:-1, :-2]
        + gray_pixels[1:-1, 2:]
        - 4.0 * center
    )
    return float(laplacian.var())


def image_fraction(box_xyxy: Sequence[float], width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    x0, y0, x1, y1 = [float(v) for v in box_xyxy]
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return area / float(width * height)


def gate_report(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    results = list(results)
    reason_counts: Dict[str, int] = {}
    gate_stats: Dict[str, Dict[str, int]] = {}
    status_counts: Dict[str, int] = {}
    for result in results:
        status = str(result["quality_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        final_reason = result.get("failure_reason")
        if final_reason:
            reason_counts[str(final_reason)] = reason_counts.get(str(final_reason), 0) + 1
        for gate in result.get("gates", []):
            name = str(gate["gate"])
            stats = gate_stats.setdefault(name, {"passed": 0, "failed": 0, "skipped": 0, "soft_pass": 0})
            outcome = str(gate["outcome"])
            if outcome in stats:
                stats[outcome] += 1
    return {
        "seen": len(results),
        "status_counts": status_counts,
        "failure_reason_counts": reason_counts,
        "gate_stats": gate_stats,
    }


def is_trusted_catalog_record(record: Dict[str, Any] | None) -> bool:
    if not record:
        return False
    source_kind = str(record.get("source_kind") or "").strip().lower()
    source_channel = str(record.get("source_channel") or "").strip().lower()
    return source_kind in {"official", "marketplace"} or source_channel in {"ecommerce", "marketplace"}


def evaluate_image_quality(
    *,
    image_id: str,
    record: Dict[str, Any] | None,
    image_path: str | Path,
    image_phash: str | None,
    accepted_phashes: List[str],
    clip_scorer: CLIPLogoQualityScorer | None,
    prescreener: YOLOWorldLogoPrescreener | None,
    min_width: int = 256,
    min_height: int = 256,
    allowed_formats: Sequence[str] = tuple(DEFAULT_ALLOWED_FORMATS),
    blur_threshold: float = 45.0,
    clip_threshold: float = 0.22,
    clip_soft_floor: float = 0.08,
    phash_distance_threshold: int = 6,
) -> Dict[str, Any]:
    now = utcnow_iso()
    quality_status = "passed"
    failure_reason = None
    quality_components: List[float] = []
    difficulty_flags: List[str] = []
    gates: List[Dict[str, Any]] = []
    trusted_catalog = is_trusted_catalog_record(record)

    if not image_path:
        return {
            "image_id": image_id,
            "quality_status": "error",
            "quality_score": 0.0,
            "failure_reason": "missing_local_image",
            "gates": [{"gate": "file", "outcome": "failed", "reason": "missing_local_image"}],
            "difficulty_flags": [],
            "quality_gate_json": json_text({"gates": [{"gate": "file", "outcome": "failed", "reason": "missing_local_image"}]}),
            "difficulty_flags_json": json_text([]),
            "last_gated_at": now,
            "updated_at": now,
        }

    path = Path(image_path)
    if not path.exists():
        return {
            "image_id": image_id,
            "quality_status": "error",
            "quality_score": 0.0,
            "failure_reason": "missing_local_image",
            "gates": [{"gate": "file", "outcome": "failed", "reason": "missing_local_image"}],
            "difficulty_flags": [],
            "quality_gate_json": json_text({"gates": [{"gate": "file", "outcome": "failed", "reason": "missing_local_image"}]}),
            "difficulty_flags_json": json_text([]),
            "last_gated_at": now,
            "updated_at": now,
        }
    if not path.is_file():
        return {
            "image_id": image_id,
            "quality_status": "error",
            "quality_score": 0.0,
            "failure_reason": "invalid_local_image_path",
            "gates": [{"gate": "file", "outcome": "failed", "reason": "invalid_local_image_path", "path": str(path)}],
            "difficulty_flags": [],
            "quality_gate_json": json_text(
                {"gates": [{"gate": "file", "outcome": "failed", "reason": "invalid_local_image_path", "path": str(path)}]}
            ),
            "difficulty_flags_json": json_text([]),
            "last_gated_at": now,
            "updated_at": now,
        }

    try:
        image_ctx = Image.open(path)
    except Exception as exc:
        return {
            "image_id": image_id,
            "quality_status": "error",
            "quality_score": 0.0,
            "failure_reason": "image_open_error",
            "gates": [{"gate": "file", "outcome": "failed", "reason": "image_open_error", "error": str(exc), "path": str(path)}],
            "difficulty_flags": [],
            "quality_gate_json": json_text(
                {"gates": [{"gate": "file", "outcome": "failed", "reason": "image_open_error", "error": str(exc), "path": str(path)}]}
            ),
            "difficulty_flags_json": json_text([]),
            "last_gated_at": now,
            "updated_at": now,
        }

    with image_ctx as image:
        image = image.convert("RGB")
        width, height = image.size
        image_format = str(getattr(image, "format", None) or path.suffix.replace(".", "").upper() or "UNKNOWN")
        allowed = {fmt.upper() for fmt in allowed_formats}
        if width < min_width or height < min_height or image_format.upper() not in allowed:
            reasons = []
            if width < min_width or height < min_height:
                reasons.append("too_small")
            if image_format.upper() not in allowed:
                reasons.append("unsupported_format")
            quality_status = "filtered"
            failure_reason = reasons[0]
            gates.append(
                {
                    "gate": "size_format",
                    "outcome": "failed",
                    "reason": reasons,
                    "width": width,
                    "height": height,
                    "format": image_format,
                }
            )
        else:
            gates.append(
                {
                    "gate": "size_format",
                    "outcome": "passed",
                    "width": width,
                    "height": height,
                    "format": image_format,
                }
            )
            quality_components.append(min(1.0, min(width / float(min_width), height / float(min_height))))

        if quality_status == "passed":
            gray = np.asarray(image.convert("L"), dtype=np.float32)
            blur_score = laplacian_variance(gray) if width >= 3 and height >= 3 else 0.0
            if blur_score < blur_threshold:
                quality_status = "filtered"
                failure_reason = "too_blurry"
                gates.append({"gate": "blur", "outcome": "failed", "blur_score": blur_score})
            else:
                gates.append({"gate": "blur", "outcome": "passed", "blur_score": blur_score})
                quality_components.append(min(1.0, blur_score / (blur_threshold * 2.0)))

        if quality_status == "passed" and image_phash:
            nearest_distance = None
            for accepted in accepted_phashes:
                distance = phash_hamming_distance(image_phash, accepted)
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                if distance <= phash_distance_threshold:
                    quality_status = "filtered"
                    failure_reason = "near_duplicate"
                    gates.append(
                        {
                            "gate": "dedupe",
                            "outcome": "failed",
                            "phash_distance": distance,
                            "threshold": phash_distance_threshold,
                        }
                    )
                    break
            if quality_status == "passed":
                gates.append(
                    {
                        "gate": "dedupe",
                        "outcome": "passed",
                        "phash_distance": nearest_distance,
                        "threshold": phash_distance_threshold,
                    }
                )
                quality_components.append(1.0)

        if quality_status == "passed" and clip_scorer is not None:
            clip_result = clip_scorer.score(image, prompt="a photo with a brand logo")
            clip_score = clip_result.get("score")
            if clip_score is None:
                gates.append({"gate": "clip_logo", "outcome": "skipped", "error": clip_result.get("error")})
            elif float(clip_score) < clip_threshold:
                clip_score_value = float(clip_score)
                if trusted_catalog and clip_score_value >= clip_soft_floor:
                    difficulty_flags.append("low_clip_logo_score")
                    gates.append(
                        {
                            "gate": "clip_logo",
                            "outcome": "soft_pass",
                            "score": clip_score_value,
                            "threshold": clip_threshold,
                            "soft_floor": clip_soft_floor,
                            "model_id": clip_result.get("model_id"),
                        }
                    )
                    quality_components.append(min(1.0, max(0.0, (clip_score_value + 1.0) / 2.0)))
                else:
                    quality_status = "filtered"
                    failure_reason = "low_clip_logo_score"
                    gates.append(
                        {
                            "gate": "clip_logo",
                            "outcome": "failed",
                            "score": clip_score_value,
                            "threshold": clip_threshold,
                            "soft_floor": clip_soft_floor,
                            "model_id": clip_result.get("model_id"),
                        }
                    )
            else:
                gates.append(
                    {
                        "gate": "clip_logo",
                        "outcome": "passed",
                        "score": float(clip_score),
                        "threshold": clip_threshold,
                        "model_id": clip_result.get("model_id"),
                    }
                )
                quality_components.append(min(1.0, max(0.0, (float(clip_score) + 1.0) / 2.0)))

        if quality_status == "passed" and prescreener is not None:
            prescreen = prescreener.detect(image)
            detections = prescreen.get("detections") or []
            if prescreen.get("error"):
                gates.append({"gate": "logo_prescreen", "outcome": "skipped", "error": prescreen.get("error")})
            elif not detections:
                difficulty_flags.append("no_logo_prescreen_detection")
                difficulty_flags.append("hard_logo_candidate")
                gates.append(
                    {
                        "gate": "logo_prescreen",
                        "outcome": "soft_pass",
                        "detections": [],
                        "model_id": prescreen.get("model_id"),
                    }
                )
            else:
                best = detections[0]
                gates.append(
                    {
                        "gate": "logo_prescreen",
                        "outcome": "passed",
                        "detections": detections,
                        "model_id": prescreen.get("model_id"),
                    }
                )
                quality_components.append(float(best["score"]))
                box_fraction = image_fraction(best["bbox_xyxy"], width, height)
                if box_fraction < 0.02:
                    difficulty_flags.append("small_logo_candidate")
                if len(detections) > 1:
                    difficulty_flags.append("multi_logo_candidate")
                if box_fraction > 0.35:
                    difficulty_flags.append("large_logo_candidate")

    quality_score = round(sum(quality_components) / len(quality_components), 4) if quality_components else 0.0
    return {
        "image_id": image_id,
        "quality_status": quality_status,
        "quality_score": quality_score,
        "failure_reason": failure_reason,
        "gates": gates,
        "difficulty_flags": sorted(set(difficulty_flags)),
        "quality_gate_json": json_text({"failure_reason": failure_reason, "gates": gates}),
        "difficulty_flags_json": json_text(sorted(set(difficulty_flags))),
        "last_gated_at": now,
        "updated_at": now,
    }
