from __future__ import annotations

from typing import Any, Dict, Iterable, List


REVIEW_BUCKET_AUTO_ACCEPT = "auto_accept"
REVIEW_BUCKET_SPOT_CHECK = "spot_check"
REVIEW_BUCKET_MUST_REVIEW = "must_review"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _contains_any(needle: str, haystack_values: Iterable[str]) -> bool:
    needle_norm = _normalize_text(needle)
    if not needle_norm:
        return False
    for candidate in haystack_values:
        candidate_norm = _normalize_text(candidate)
        if candidate_norm and (candidate_norm in needle_norm or needle_norm in candidate_norm):
            return True
    return False


def _check_payload(name: str, status: str, detail: str, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "evidence": evidence or {},
    }


def verify_text_consistency(
    *,
    record: Dict[str, Any],
    merged: Dict[str, Any],
    brand_record: Dict[str, Any] | None,
    qwen_structured: Dict[str, Any] | None,
) -> Dict[str, Any]:
    knowledge = (qwen_structured or {}).get("knowledge_json") or {}
    recognition = knowledge.get("recognition") or {}
    world_knowledge = knowledge.get("world_knowledge") or {}
    ambiguity = knowledge.get("ambiguity") or {}
    validation = (qwen_structured or {}).get("validation") or {"valid": False, "errors": ["missing_qwen_validation"]}

    checks: List[Dict[str, Any]] = []

    if validation.get("valid"):
        checks.append(_check_payload("schema", "verified", "qwen schema valid"))
    else:
        checks.append(
            _check_payload(
                "schema",
                "unsupported",
                "qwen schema invalid",
                {"errors": list(validation.get("errors") or [])},
            )
        )

    merged_brand_name = merged.get("merged_brand_name")
    qwen_brand = recognition.get("brand")
    alias_pool = _string_list((brand_record or {}).get("aliases_en"))
    alias_pool.extend(_string_list((brand_record or {}).get("label")))
    alias_pool.extend(_string_list((brand_record or {}).get("query")))
    alias_pool.extend(_string_list((brand_record or {}).get("display_name")))
    alias_pool.extend(_string_list((brand_record or {}).get("canonical_name")))
    alias_pool.extend(_string_list(record.get("brand")))

    if qwen_brand:
        if _contains_any(qwen_brand, [merged_brand_name] + alias_pool):
            checks.append(
                _check_payload(
                    "brand_match",
                    "verified",
                    "qwen brand agrees with metadata/ontology",
                    {"merged_brand_name": merged_brand_name, "qwen_brand": qwen_brand},
                )
            )
        else:
            checks.append(
                _check_payload(
                    "brand_match",
                    "conflict",
                    "qwen brand conflicts with metadata/ontology",
                    {"merged_brand_name": merged_brand_name, "qwen_brand": qwen_brand},
                )
            )
    else:
        checks.append(_check_payload("brand_match", "unsupported", "qwen did not provide brand"))

    qwen_industry = world_knowledge.get("industry")
    ontology_industries = _string_list((brand_record or {}).get("industries"))
    if qwen_industry and ontology_industries:
        if _contains_any(qwen_industry, ontology_industries):
            checks.append(
                _check_payload(
                    "industry_match",
                    "verified",
                    "industry agrees with ontology",
                    {"qwen_industry": qwen_industry, "ontology_industries": ontology_industries},
                )
            )
        else:
            checks.append(
                _check_payload(
                    "industry_match",
                    "conflict",
                    "industry conflicts with ontology",
                    {"qwen_industry": qwen_industry, "ontology_industries": ontology_industries},
                )
            )
    elif qwen_industry:
        checks.append(_check_payload("industry_match", "likely_valid", "industry inferred but ontology has no comparison value"))
    else:
        checks.append(_check_payload("industry_match", "unsupported", "no industry claim"))

    qwen_parent = recognition.get("parent_company")
    ontology_parents = _string_list((brand_record or {}).get("parent_organizations"))
    if qwen_parent and ontology_parents:
        if _contains_any(qwen_parent, ontology_parents):
            checks.append(
                _check_payload(
                    "parent_match",
                    "verified",
                    "parent company agrees with ontology",
                    {"qwen_parent": qwen_parent, "ontology_parents": ontology_parents},
                )
            )
        else:
            checks.append(
                _check_payload(
                    "parent_match",
                    "conflict",
                    "parent company conflicts with ontology",
                    {"qwen_parent": qwen_parent, "ontology_parents": ontology_parents},
                )
            )
    elif qwen_parent:
        checks.append(_check_payload("parent_match", "likely_valid", "parent company inferred without ontology reference"))
    else:
        checks.append(_check_payload("parent_match", "unsupported", "no parent-company claim"))

    category = _normalize_text(record.get("category"))
    services = " ".join(_string_list(world_knowledge.get("products_services")))
    if category and services:
        if _contains_any(category, [services]):
            checks.append(
                _check_payload(
                    "category_relation",
                    "verified",
                    "products/services align with record category",
                    {"category": category, "products_services": world_knowledge.get("products_services")},
                )
            )
        else:
            checks.append(
                _check_payload(
                    "category_relation",
                    "likely_valid",
                    "category relation is weak",
                    {"category": category, "products_services": world_knowledge.get("products_services")},
                )
            )
    else:
        checks.append(_check_payload("category_relation", "unsupported", "insufficient category evidence"))

    scene_reasonableness = _normalize_text(world_knowledge.get("scene_reasonableness"))
    if scene_reasonableness:
        if any(token in scene_reasonableness for token in ("unlikely", "implausible", "suspicious", "unreasonable")):
            checks.append(
                _check_payload(
                    "scene_reasonableness",
                    "conflict",
                    "qwen marked the scene as unlikely",
                    {"scene_reasonableness": world_knowledge.get("scene_reasonableness")},
                )
            )
        else:
            checks.append(
                _check_payload(
                    "scene_reasonableness",
                    "likely_valid",
                    "scene is not obviously problematic",
                    {"scene_reasonableness": world_knowledge.get("scene_reasonableness")},
                )
            )
    else:
        checks.append(_check_payload("scene_reasonableness", "unsupported", "no scene reasonableness claim"))

    if ambiguity.get("needs_human_review") is True:
        checks.append(
            _check_payload(
                "ambiguity",
                "conflict",
                "qwen requested human review",
                {"uncertain_fields": ambiguity.get("uncertain_fields"), "note": ambiguity.get("note")},
            )
        )
    elif ambiguity:
        checks.append(
            _check_payload(
                "ambiguity",
                "likely_valid",
                "ambiguity section present without explicit review request",
                {"uncertain_fields": ambiguity.get("uncertain_fields"), "note": ambiguity.get("note")},
            )
        )
    else:
        checks.append(_check_payload("ambiguity", "unsupported", "no ambiguity payload"))

    status_counts = {"verified": 0, "likely_valid": 0, "conflict": 0, "unsupported": 0}
    for check in checks:
        status_counts[check["status"]] = status_counts.get(check["status"], 0) + 1

    if status_counts["conflict"] > 0:
        overall_status = "conflict"
        score = 0.35
    elif status_counts["verified"] >= 2:
        overall_status = "verified"
        score = 0.95
    elif status_counts["verified"] + status_counts["likely_valid"] >= 2:
        overall_status = "likely_valid"
        score = 0.75
    else:
        overall_status = "unsupported"
        score = 0.45

    return {
        "overall_status": overall_status,
        "verification_score": round(score, 4),
        "status_counts": status_counts,
        "checks": checks,
    }


def classify_review_bucket(
    *,
    confidence: float,
    verification_payload: Dict[str, Any],
    brand_id: str | None,
) -> Dict[str, str]:
    verification_status = str(verification_payload.get("overall_status") or "unsupported")
    if verification_status == "conflict" or confidence < 0.75:
        bucket = REVIEW_BUCKET_MUST_REVIEW
    elif verification_status == "verified" and brand_id and confidence >= 0.92:
        bucket = REVIEW_BUCKET_AUTO_ACCEPT
    else:
        bucket = REVIEW_BUCKET_SPOT_CHECK
    return {
        "review_bucket": bucket,
        "review_status": "auto_accept" if bucket == REVIEW_BUCKET_AUTO_ACCEPT else "needs_review",
    }

