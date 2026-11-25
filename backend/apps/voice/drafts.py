"""Validated drafts for AI interpretation (AI-02, AI-04, WK-01, JOB-01).

Pipeline: provider RAW output → ``validate_raw`` (strict types; failure =
``ai_output_invalid``) → ``build_draft`` (catalog mapping, negation, missing and
uncertain fields) → user ``corrections`` (validated by ``clean_corrections``) →
``confirm`` (required fields + consistency rules). The model can only ever produce a
draft; it never publishes a profile or creates a job.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from rest_framework.exceptions import ErrorDetail, ValidationError

from apps.catalog.models import Area, ServiceTag, Trade
from apps.providers.errors import ProviderInvalidOutput

SCHEMA_VERSION = "1"

# field name -> type: text:<max> | trade | services | area | int:<min>:<max>
FIELD_TYPES: dict[str, dict[str, str]] = {
    "worker_introduction": {
        "name": "text:80",
        "trade": "trade",
        "years_experience": "int:0:70",
        "services_offered": "services",
        "services_not_offered": "services",
    },
    "job_description": {
        "description": "text:1000",
        "trade": "trade",
        "services": "services",
        "services_excluded": "services",
        "area": "area",
        "preferred_time_text": "text:120",
        "budget_pkr": "int:0:10000000",
    },
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "worker_introduction": ("name", "trade"),
    "job_description": ("description", "trade", "area", "preferred_time_text"),
}
# (positive list, negated list) per kind
SERVICE_LISTS = {
    "worker_introduction": ("services_offered", "services_not_offered"),
    "job_description": ("services", "services_excluded"),
}
RAW_KEYS = {
    "worker_introduction": {"name", "trade", "years_experience", "service_mentions", "uncertain_fields"},
    "job_description": {
        "description", "trade", "service_mentions", "area_phrase", "area_code",
        "preferred_time_text", "budget_pkr", "uncertain_fields",
    },
}


@dataclass(frozen=True)
class CatalogIndex:
    trades: frozenset[str]
    services: dict[str, str]  # service code -> trade code
    areas: frozenset[str]

    @classmethod
    def load(cls) -> "CatalogIndex":
        return cls(
            trades=frozenset(Trade.objects.filter(is_active=True).values_list("code", flat=True)),
            services=dict(
                ServiceTag.objects.filter(is_active=True, trade__is_active=True).values_list("code", "trade__code")
            ),
            areas=frozenset(Area.objects.filter(is_active=True, city__is_active=True).values_list("code", flat=True)),
        )

    def fingerprint(self) -> str:
        payload = json.dumps([sorted(self.trades), sorted(self.services.items()), sorted(self.areas)])
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def catalog_context(kind: str) -> dict[str, Any]:
    """Reference data given to the provider (codes + bilingual labels; nothing private)."""
    context: dict[str, Any] = {
        "trades": [
            {"code": t.code, "en": t.label_en, "ur": t.label_ur} for t in Trade.objects.filter(is_active=True)
        ],
        "services": [
            {"code": s.code, "trade": s.trade.code, "en": s.label_en, "ur": s.label_ur}
            for s in ServiceTag.objects.filter(is_active=True, trade__is_active=True).select_related("trade")
        ],
    }
    if kind == "job_description":
        context["areas"] = [
            {"code": a.code, "city": a.city.code, "en": a.label_en, "ur": a.label_ur}
            for a in Area.objects.filter(is_active=True, city__is_active=True).select_related("city")
        ]
    return context


# --- Raw output validation -----------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_raw(kind: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProviderInvalidOutput("draft_not_object")
    missing = RAW_KEYS[kind] - raw.keys()
    if missing:
        raise ProviderInvalidOutput("draft_missing_keys")
    for key in RAW_KEYS[kind] - {"service_mentions", "uncertain_fields", "years_experience", "budget_pkr"}:
        if raw[key] is not None and not isinstance(raw[key], str):
            raise ProviderInvalidOutput(f"draft_bad_type:{key}")
    for key in {"years_experience", "budget_pkr"} & RAW_KEYS[kind]:
        if raw[key] is not None and not _is_int(raw[key]):
            raise ProviderInvalidOutput(f"draft_bad_type:{key}")
    mentions = raw["service_mentions"]
    if not isinstance(mentions, list) or len(mentions) > 50:
        raise ProviderInvalidOutput("draft_bad_type:service_mentions")
    for mention in mentions:
        if (
            not isinstance(mention, dict)
            or not isinstance(mention.get("phrase"), str)
            or not (mention.get("service_code") is None or isinstance(mention.get("service_code"), str))
            or not isinstance(mention.get("negated"), bool)
        ):
            raise ProviderInvalidOutput("draft_bad_mention")
    uncertain = raw["uncertain_fields"]
    if not isinstance(uncertain, list) or not all(isinstance(item, str) for item in uncertain):
        raise ProviderInvalidOutput("draft_bad_type:uncertain_fields")
    return {key: raw[key] for key in RAW_KEYS[kind]}  # extra keys are dropped, never used


# --- Draft construction ----------------------------------------------------------------


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def build_draft(kind: str, raw: dict[str, Any], source_text: str, catalog: CatalogIndex) -> dict[str, Any]:
    field_names = FIELD_TYPES[kind]
    uncertain = {name for name in raw["uncertain_fields"] if name in field_names}
    heard: dict[str, str] = {}
    fields: dict[str, Any] = {}

    trade = (raw.get("trade") or "").strip() or None
    if trade and trade not in catalog.trades:
        heard["trade"] = trade[:80]
        trade, _ = None, uncertain.add("trade")
    fields["trade"] = trade

    positive_key, negated_key = SERVICE_LISTS[kind]
    positive: list[str] = []
    negated: list[str] = []
    unmatched: list[dict[str, Any]] = []
    for mention in raw["service_mentions"]:
        code = (mention["service_code"] or "").strip() or None
        phrase = mention["phrase"].strip()[:200]
        if code and code not in catalog.services:
            code = None
        if code is None:
            if phrase:
                unmatched.append({"phrase": phrase, "negated": mention["negated"]})
            continue
        target = negated if mention["negated"] else positive
        if code not in target:
            target.append(code)
    conflicting = set(positive) & set(negated)
    if conflicting:
        # Said both ways: keep neither and ask, rather than guess (AI-04).
        positive = [c for c in positive if c not in conflicting]
        negated = [c for c in negated if c not in conflicting]
        uncertain.update({positive_key, negated_key})
    fields[positive_key] = positive
    fields[negated_key] = negated

    if kind == "worker_introduction":
        name = (raw.get("name") or "").strip() or None
        if name and _normalise(name) not in _normalise(source_text):
            heard["name"] = name[:80]
            name, _ = None, uncertain.add("name")  # never accept a name that was not said
        fields["name"] = name[:80] if name else None
        years = raw.get("years_experience")
        if years is not None and not 0 <= years <= 70:
            years, _ = None, uncertain.add("years_experience")
        fields["years_experience"] = years
    else:
        description = (raw.get("description") or "").strip() or None
        fields["description"] = description[:1000] if description else None
        area = (raw.get("area_code") or "").strip() or None
        area_phrase = (raw.get("area_phrase") or "").strip() or None
        if area and area not in catalog.areas:
            area = None
        if area is None and area_phrase:
            heard["area"] = area_phrase[:120]
            uncertain.add("area")
        fields["area"] = area
        time_text = (raw.get("preferred_time_text") or "").strip() or None
        fields["preferred_time_text"] = time_text[:120] if time_text else None
        budget = raw.get("budget_pkr")
        if budget is not None and budget < 0:
            budget, _ = None, uncertain.add("budget_pkr")
        fields["budget_pkr"] = budget

    missing = [name for name in REQUIRED[kind] if _empty(fields.get(name))]
    return {
        "fields": {name: fields.get(name) for name in field_names},
        "missing": missing,
        "uncertain": sorted(uncertain - set(missing)),
        "unmatched_mentions": unmatched[:20],
        "heard": heard,
    }


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


# --- User corrections and confirmation -------------------------------------------------


def _error(code: str, message: str) -> list[ErrorDetail]:
    return [ErrorDetail(message, code=code)]


def clean_corrections(kind: str, data: Any, catalog: CatalogIndex) -> dict[str, Any]:
    """Validate a PATCH {"fields": {...}}. Only known fields; codes must be active catalog entries."""
    if not isinstance(data, dict) or set(data) != {"fields"} or not isinstance(data["fields"], dict):
        raise ValidationError({"fields": _error("invalid", "Send corrections as {\"fields\": {...}}.")})
    errors: dict[str, list[ErrorDetail]] = {}
    cleaned: dict[str, Any] = {}
    for name, value in data["fields"].items():
        field_type = FIELD_TYPES[kind].get(name)
        if field_type is None:
            errors[name] = _error("unexpected_field", "This field is not accepted.")
            continue
        try:
            cleaned[name] = _clean_value(field_type, value, catalog)
        except ValueError as exc:
            errors[name] = _error(str(exc), "Invalid value.")
    if errors:
        raise ValidationError({"fields": errors})
    return cleaned


def _clean_value(field_type: str, value: Any, catalog: CatalogIndex) -> Any:
    kind, *args = field_type.split(":")
    if kind == "text":
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid")
        value = value.strip()
        if len(value) > int(args[0]):
            raise ValueError("max_length")
        return value or None
    if kind == "int":
        if value is None:
            return None
        if not _is_int(value) or not int(args[0]) <= value <= int(args[1]):
            raise ValueError("invalid")
        return value
    if kind == "trade":
        if value is None:
            return None
        if value not in catalog.trades:
            raise ValueError("unknown_trade")
        return value
    if kind == "area":
        if value is None:
            return None
        if value not in catalog.areas:
            raise ValueError("unknown_area")
        return value
    if kind == "services":
        if not isinstance(value, list) or len(value) > 50 or not all(isinstance(v, str) for v in value):
            raise ValueError("invalid")
        if any(v not in catalog.services for v in value):
            raise ValueError("unknown_service")
        return list(dict.fromkeys(value))
    raise ValueError("invalid")


def effective_fields(draft: dict[str, Any], corrections: dict[str, Any]) -> dict[str, Any]:
    return {**draft["fields"], **corrections}


def validate_for_confirmation(kind: str, fields: dict[str, Any]) -> None:
    errors: dict[str, list[ErrorDetail]] = {}
    for name in REQUIRED[kind]:
        if _empty(fields.get(name)):
            errors[name] = _error("required", "This field is required before confirming.")
    positive_key, negated_key = SERVICE_LISTS[kind]
    if set(fields.get(positive_key) or []) & set(fields.get(negated_key) or []):
        errors[negated_key] = _error(
            "offered_and_excluded_overlap", "A service cannot be both included and excluded."
        )
    if errors:
        raise ValidationError({"fields": errors})


def input_hash(kind: str, language: str, text: str, provider: str, model: str, catalog: CatalogIndex) -> str:
    payload = json.dumps([SCHEMA_VERSION, kind, language, text, provider, model, catalog.fingerprint()], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
