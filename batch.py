from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Tuple


def configured_pair_count() -> int:
    from multi_brand_fetcher import BRAND_SOURCES

    return len(BRAND_SOURCES)


def default_limit_per_pair(target_records: int) -> int:
    pairs = max(configured_pair_count(), 1)
    return max(1, math.ceil(target_records / pairs))


def load_records(path: str | Path) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Expected JSON list in {path}")
    return payload


def save_records(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(rows), ensure_ascii=False, indent=2), encoding="utf-8")


def batch_bucket_key(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(record.get("brand") or "unknown"),
        str(record.get("category") or "unknown"),
        str(record.get("source_channel") or "unknown"),
        str(record.get("source") or "unknown"),
    )


def rebalance_records(records: Iterable[Dict[str, Any]], target_records: int) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(batch_bucket_key(record), []).append(record)

    ordered_keys = sorted(grouped)
    buckets: List[Deque[Dict[str, Any]]] = [deque(grouped[key]) for key in ordered_keys]
    selected: List[Dict[str, Any]] = []

    while len(selected) < target_records:
        made_progress = False
        for bucket in buckets:
            if not bucket:
                continue
            selected.append(bucket.popleft())
            made_progress = True
            if len(selected) >= target_records:
                break
        if not made_progress:
            break

    return selected
