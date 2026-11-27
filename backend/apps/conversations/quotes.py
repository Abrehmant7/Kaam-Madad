"""Quotation rules, totals, gap checks and readiness (QT-01..03, GAP-01..03).

- ``validate(fields)``: deterministic rules a quote must pass before it can be submitted (required
  fields, valid amounts, timing). Returned as field errors; a submitted version always passed them.
- ``compute_totals``: Decimal arithmetic only. Unknown amounts stay unknown (``None``), and the total
  says which parts are unknown instead of treating them as zero.
- ``rule_findings``: deterministic clarification prompts stored with a submitted version (e.g. the
  proposed time is outside the customer's requested window).
- ``run_ai_check``: the agreement-check provider on the text needed for the check only; provider
  failure is recorded as "unavailable", never as a pass.
- ``readiness``: the M8 hand-off. M8 must re-check it inside its booking transaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.invitations.models import Invitation
from apps.providers import registry
from apps.providers.errors import ProviderError
from apps.workers.eligibility import worker_eligibility

from .models import GapFinding, Message, Quote

KARACHI = ZoneInfo("Asia/Karachi")


def iso_utc(value: datetime | None) -> str | None:
    """The API's timestamp format: UTC with a "Z" suffix."""
    return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z") if value else None


def _karachi(value: datetime | str | None) -> str | None:
    """One time format for the agreement check (Asia/Karachi, +05:00), so equal instants look equal."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(KARACHI).isoformat(timespec="minutes")

logger = logging.getLogger(__name__)
MAX_AMOUNT = Decimal("10000000")
MAX_DAYS_AHEAD = 90
TWO_PLACES = Decimal("0.01")


def validate(quote: Quote, now: datetime | None = None) -> dict[str, list[tuple[str, str]]]:
    now = now or timezone.now()
    errors: dict[str, list[tuple[str, str]]] = {}

    def add(name: str, code: str, message: str) -> None:
        errors.setdefault(name, []).append((code, message))

    if not quote.scope.strip():
        add("scope", "required", "Describe the work this quote covers.")
    for name in ("labour_amount", "materials_amount", "visit_fee"):
        value = getattr(quote, name)
        if value is not None and not (Decimal("0") <= value <= MAX_AMOUNT):
            add(name, "amount_out_of_range", "Enter an amount between 0 and 10,000,000 PKR.")
    if quote.inspection_only:
        if quote.visit_fee in (None, Decimal("0")):
            add("visit_fee", "required", "An inspection-only quote must state the inspection fee.")
        if quote.visit_fee_treatment not in (Quote.VisitFee.CHARGED, Quote.VisitFee.WAIVED_IF_HIRED):
            add("visit_fee_treatment", "inspection_fee_treatment", "Say whether the inspection fee is charged or waived.")
    else:
        if quote.labour_amount is None:
            add("labour_amount", "required", "Enter the labour amount.")
        if quote.labour_basis == Quote.LabourBasis.PER_ITEM and not quote.quantity:
            add("quantity", "required", "Enter the number of items for a per-item price.")
        if not quote.materials:
            add("materials", "required", "Say who supplies and pays for the materials.")
    if quote.materials_amount is not None and quote.materials != Quote.Materials.WORKER_EXTRA:
        add("materials_amount", "materials_amount_not_applicable", "A materials amount applies only when charged separately.")
    if quote.visit_fee_treatment == Quote.VisitFee.NONE and quote.visit_fee not in (None, Decimal("0")):
        add("visit_fee_treatment", "visit_fee_treatment_missing", "Say how the visit fee is treated.")
    if quote.visit_fee_treatment in (Quote.VisitFee.CHARGED, Quote.VisitFee.WAIVED_IF_HIRED) and not quote.visit_fee:
        add("visit_fee", "required", "Enter the visit fee.")
    if quote.quantity is not None and not 1 <= quote.quantity <= 999:
        add("quantity", "quantity_out_of_range", "Enter a quantity between 1 and 999.")
    if not quote.start_at:
        add("start_at", "required", "Choose the proposed start time.")
    if not quote.end_at:
        add("end_at", "required", "Choose the proposed end time.")
    if quote.start_at and quote.end_at and quote.end_at <= quote.start_at:
        add("end_at", "window_end_before_start", "The end time must be after the start time.")
    if quote.start_at and quote.start_at < now:
        add("start_at", "window_in_past", "Choose a time that has not passed.")
    if quote.start_at and quote.start_at > now + timedelta(days=MAX_DAYS_AHEAD):
        add("start_at", "window_too_far", "Choose a date within 90 days.")
    return errors


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(TWO_PLACES))


def compute_totals(quote: Quote) -> dict:
    """Backend arithmetic (Decimal). ``None`` = unknown, listed in ``unknown``; never treated as zero."""
    unknown: list[str] = []
    labour = None
    if quote.labour_amount is not None:
        labour = quote.labour_amount * (quote.quantity or 1) if quote.labour_basis == Quote.LabourBasis.PER_ITEM else quote.labour_amount
    elif not quote.inspection_only:
        unknown.append("labour")
    if quote.inspection_only and quote.labour_amount is None:
        unknown.append("repair")
    materials = Decimal("0")
    if quote.materials == Quote.Materials.WORKER_EXTRA:
        materials = quote.materials_amount
        if materials is None:
            unknown.append("materials")
    visit = quote.visit_fee if quote.visit_fee_treatment == Quote.VisitFee.CHARGED else Decimal("0")
    if quote.inspection_only and quote.visit_fee_treatment == Quote.VisitFee.WAIVED_IF_HIRED:
        visit = quote.visit_fee  # payable for the inspection; waived only if the repair goes ahead later
    known = sum((part for part in (labour, materials, visit) if part is not None), Decimal("0"))
    return {
        "labour_total": _money(labour),
        "materials_total": _money(materials),
        "visit_total": _money(visit),
        "known_total": _money(known),
        "unknown": unknown,
        "complete": not unknown,
    }


def rule_findings(quote: Quote) -> list[dict]:
    """Deterministic clarification prompts for a submitted version (customer must confirm changes)."""
    findings = []
    shared = quote.invitation.shared_summary
    requested_start = datetime.fromisoformat(shared["window_start"].replace("Z", "+00:00"))
    requested_end = datetime.fromisoformat(shared["window_end"].replace("Z", "+00:00"))
    if quote.start_at < requested_start or quote.end_at > requested_end:
        findings.append({
            "code": "timing_differs", "ask": "customer", "blocking": True,
            "question": "The proposed time is outside the time you requested. Is the new time acceptable?",
            "sources": [
                {"kind": "request", "ref": "window", "text": f"{shared['window_start']} – {shared['window_end']}"},
                {"kind": "quote", "ref": "start_at", "text": f"{iso_utc(quote.start_at)} – {iso_utc(quote.end_at)}"},
            ],
        })
    if quote.materials == Quote.Materials.WORKER_EXTRA and quote.materials_amount is None:
        findings.append({
            "code": "materials_amount_unknown", "ask": "customer", "blocking": False,
            "question": "The materials cost is not known yet. It will be added separately.",
            "sources": [{"kind": "quote", "ref": "materials_amount", "text": "unknown"}],
        })
    return findings


def quote_terms(quote: Quote) -> dict:
    """The structured terms sent to the agreement check (no identities, no private details)."""
    return {
        "inspection_only": quote.inspection_only,
        "scope": quote.scope,
        "quantity": quote.quantity,
        "labour_amount_pkr": _money(quote.labour_amount),
        "labour_basis": quote.labour_basis,
        "materials": quote.materials,
        "materials_amount_pkr": _money(quote.materials_amount),
        "visit_fee_pkr": _money(quote.visit_fee),
        "visit_fee_treatment": quote.visit_fee_treatment,
        "exclusions": quote.exclusions,
        "start_at": _karachi(quote.start_at),
        "end_at": _karachi(quote.end_at),
    }


def check_inputs(quote: Quote) -> tuple[dict, list[dict], dict]:
    shared = quote.invitation.shared_summary
    request = {key: shared[key] for key in ("description", "trade", "services", "services_excluded", "area",
                                              "window_start", "window_end", "budget_preference_pkr")}
    request["window_start"], request["window_end"] = _karachi(shared["window_start"]), _karachi(shared["window_end"])
    messages = [
        {"id": str(m.id), "role": m.sender_role, "text": m.text}
        for m in Message.objects.filter(invitation=quote.invitation).order_by("created_at")
        if m.text.strip()  # sender-approved text only; "caption unavailable" notes carry no text
    ][-40:]
    return request, messages, quote_terms(quote)


def run_ai_check(quote: Quote) -> None:
    """Run the agreement check for a submitted version and store its findings. Never raises."""
    request, messages, terms = check_inputs(quote)
    now = timezone.now()
    try:
        result = registry.agreement_checker().check(request=request, messages=messages, quote=terms)
    except ProviderError as exc:
        _unavailable(quote, f"{exc.code}:{exc.reason}", now)
        return
    except Exception:  # noqa: BLE001 — any other failure must also show as "could not run", never as a pass
        logger.exception("Agreement check failed unexpectedly.")
        _unavailable(quote, "ai_check_error:unexpected", now)
        return
    with transaction.atomic():
        GapFinding.objects.filter(quote=quote, source=GapFinding.Source.AI, status=GapFinding.Status.OPEN).delete()
        for finding in result.findings:
            GapFinding.objects.create(quote=quote, source=GapFinding.Source.AI, code=finding["code"], blocking=True,
                                      question=finding["question"], ask=finding["ask"], sources=finding["sources"])
        Quote.objects.filter(pk=quote.pk).update(
            check_status=Quote.CheckStatus.FINDINGS if result.findings else Quote.CheckStatus.PASSED,
            check_provider=result.provider, check_simulated=result.simulated, checked_at=now, check_failure="",
        )
    logger.info("Agreement check done (provider=%s, findings=%d).", result.provider, len(result.findings))


def _unavailable(quote: Quote, failure: str, now) -> None:
    Quote.objects.filter(pk=quote.pk).update(check_status=Quote.CheckStatus.UNAVAILABLE, checked_at=now,
                                             check_failure=failure[:64], check_provider="")
    logger.warning("Agreement check unavailable (%s).", failure.split(":")[0])


def current_quote(invitation: Invitation) -> Quote | None:
    return invitation.quotes.filter(status=Quote.Status.SUBMITTED).first()


def readiness(invitation: Invitation, quote: Quote | None = None, now: datetime | None = None) -> dict:
    """Is this quote ready for the customer to accept? (M8 re-checks inside its booking transaction.)"""
    now = now or timezone.now()
    quote = quote or current_quote(invitation)
    blocking: list[str] = []
    warnings: list[str] = []
    if invitation.status != Invitation.Status.ACTIVE:
        blocking.append("invitation_not_active")
    if quote is None:
        blocking.append("no_quote")
    else:
        if quote.status == Quote.Status.DRAFT:
            blocking.append("quote_not_submitted")
        if quote.status == Quote.Status.SUPERSEDED:
            blocking.append("quote_superseded")
        if quote.expires_at and now >= quote.expires_at:
            blocking.append("quote_expired")
        findings = list(quote.findings.all())
        if any(f.blocking and f.status == GapFinding.Status.OPEN for f in findings):
            blocking.append("unresolved_findings")
        if any(not f.blocking and f.status == GapFinding.Status.OPEN for f in findings):
            warnings.append("open_notes")
        if quote.status == Quote.Status.SUBMITTED:
            if quote.check_status == Quote.CheckStatus.NOT_RUN:
                blocking.append("automated_check_not_run")
            elif quote.check_status == Quote.CheckStatus.UNAVAILABLE and quote.manual_review_at is None:
                blocking.append("automated_check_unavailable")
        if quote.totals and not quote.totals.get("complete"):
            warnings.append("unknown_amounts")
    worker = invitation.worker_profile
    if not worker_eligibility(worker.user, worker).can_take_jobs:
        blocking.append("worker_not_eligible")
    return {
        "invitation_id": str(invitation.id),
        "quote_id": str(quote.id) if quote else None,
        "version": quote.version if quote else None,
        "expires_at": iso_utc(quote.expires_at) if quote else None,
        "ready": not blocking,
        "blocking": blocking,
        "warnings": warnings,
    }


def expiry_for(submitted_at: datetime, start_at: datetime) -> datetime:
    return min(submitted_at + timedelta(hours=settings.QUOTE_VALIDITY_HOURS), start_at)
