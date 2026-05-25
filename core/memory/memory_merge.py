from __future__ import annotations

import re
from typing import Any

CATEGORIES = {"preference", "routine", "constraint", "context"}

CLAIM_TYPES = {
    "explicit_preference",
    "implicit_preference",
    "routine",
    "device_alias",
    "constraint",
    "home_context",
}

MEMORY_STATUSES = {"candidate", "confirmed", "rejected", "stale"}

CONFIDENCE_LEVELS = {"low", "medium", "high"}


def slugify_topic(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(topic).lower()).strip("_")
    return slug[:64] or "memory"


def normalize_memory_for_storage(item: dict[str, Any]) -> dict[str, Any] | None:
    topic = slugify_topic(str(item.get("topic", "")).strip())
    if not topic:
        return None

    summary = str(item.get("summary", "")).strip()
    if not summary:
        return None

    category = _normalize_enum(item.get("category"), CATEGORIES, "context")
    claim_type = _normalize_enum(
        item.get("claim_type"),
        CLAIM_TYPES,
        _default_claim_type(category),
    )
    status = _normalize_enum(item.get("status"), MEMORY_STATUSES, "candidate")
    confidence = _normalize_enum(item.get("confidence"), CONFIDENCE_LEVELS, "low")

    positive_evidence = _normalize_evidence_list(item.get("positive_evidence"))
    negative_evidence = _normalize_evidence_list(item.get("negative_evidence"))

    payload: dict[str, Any] = {
        "topic": topic,
        "title": str(item.get("title", topic)).strip() or topic,
        "category": category,
        "claim_type": claim_type,
        "status": status,
        "summary": summary,
        "details": _normalize_string_list(item.get("details")),
        "device_types": _normalize_string_list(item.get("device_types")),
        "device_ids": _normalize_string_list(item.get("device_ids")),
        "scenes": _normalize_string_list(item.get("scenes")),
        "confidence": confidence,
        "evidence_count": len(_dedupe_evidence(positive_evidence)),
        "positive_evidence": _dedupe_evidence(positive_evidence),
        "negative_evidence": _dedupe_evidence(negative_evidence),
        "source_actions": _normalize_string_list(item.get("source_actions")),
        "created_at": str(item.get("created_at", "")).strip(),
        "updated_at": str(item.get("updated_at", "")).strip(),
    }

    linked_custom_skill_name = str(item.get("linked_custom_skill_name", "")).strip()
    if linked_custom_skill_name:
        payload["linked_custom_skill_name"] = linked_custom_skill_name

    return payload


def merge_extracted_memory(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    incoming_normalized = normalize_memory_for_storage(incoming)
    if incoming_normalized is None:
        raise ValueError("incoming memory is missing required topic or summary")

    existing_normalized = normalize_memory_for_storage(existing or {}) if existing else None
    if existing_normalized is None:
        payload = dict(incoming_normalized)
        payload["created_at"] = payload.get("created_at") or now
        payload["updated_at"] = now
        payload["status"] = resolve_memory_status(payload)
        return payload

    payload = dict(existing_normalized)
    for field in ("topic", "title", "category", "claim_type", "summary", "confidence"):
        value = incoming_normalized.get(field)
        if value:
            payload[field] = value

    payload["details"] = _merge_string_lists(
        existing_normalized.get("details"),
        incoming_normalized.get("details"),
    )
    payload["device_types"] = _merge_string_lists(
        existing_normalized.get("device_types"),
        incoming_normalized.get("device_types"),
    )
    payload["device_ids"] = _merge_string_lists(
        existing_normalized.get("device_ids"),
        incoming_normalized.get("device_ids"),
    )
    payload["scenes"] = _merge_string_lists(
        existing_normalized.get("scenes"),
        incoming_normalized.get("scenes"),
    )
    payload["source_actions"] = _merge_string_lists(
        existing_normalized.get("source_actions"),
        incoming_normalized.get("source_actions"),
    )
    payload["positive_evidence"] = _dedupe_evidence(
        [
            *existing_normalized.get("positive_evidence", []),
            *incoming_normalized.get("positive_evidence", []),
        ]
    )
    payload["negative_evidence"] = _dedupe_evidence(
        [
            *existing_normalized.get("negative_evidence", []),
            *incoming_normalized.get("negative_evidence", []),
        ]
    )
    payload["evidence_count"] = len(payload["positive_evidence"])
    payload["created_at"] = existing_normalized.get("created_at") or now
    payload["updated_at"] = now

    incoming_link = incoming_normalized.get("linked_custom_skill_name")
    existing_link = existing_normalized.get("linked_custom_skill_name")
    if incoming_link or existing_link:
        payload["linked_custom_skill_name"] = incoming_link or existing_link

    if existing_normalized.get("status") in {"rejected", "stale"}:
        payload["status"] = existing_normalized["status"]
    else:
        payload["status"] = resolve_memory_status(payload)
    return payload


def resolve_memory_status(memory: dict[str, Any]) -> str:
    status = str(memory.get("status", "candidate")).strip().lower()
    if status in {"rejected", "stale"}:
        return status

    claim_type = str(memory.get("claim_type", "home_context")).strip().lower()
    try:
        evidence_count = int(memory.get("evidence_count", 0) or 0)
    except (TypeError, ValueError):
        evidence_count = 0

    if claim_type in {"explicit_preference", "constraint"} and evidence_count >= 1:
        return "confirmed"
    if claim_type == "device_alias" and evidence_count >= 2:
        return "confirmed"
    if claim_type in {"implicit_preference", "routine"} and evidence_count >= 3:
        return "confirmed"
    if claim_type == "home_context" and evidence_count >= 2:
        return "confirmed"
    return "candidate"


def _default_claim_type(category: str) -> str:
    if category == "preference":
        return "implicit_preference"
    if category == "routine":
        return "routine"
    if category == "constraint":
        return "constraint"
    return "home_context"


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _merge_string_lists(left: Any, right: Any) -> list[str]:
    return _normalize_string_list([*_normalize_string_list(left), *_normalize_string_list(right)])


def _normalize_evidence_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id", "")).strip()
        if not event_id:
            continue
        result.append(
            {
                "event_id": event_id,
                "timestamp": str(item.get("timestamp", "")).strip(),
                "source": str(item.get("source", "")).strip(),
                "action": str(item.get("action", "")).strip(),
                "device_type": str(item.get("device_type", "")).strip(),
                "device_id": str(item.get("device_id", "")).strip(),
                "summary": str(item.get("summary", "")).strip(),
            }
        )
    return result


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        event_id = str(item.get("event_id", "")).strip()
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        result.append(item)
    return result
