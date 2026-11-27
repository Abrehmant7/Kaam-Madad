"""Urdu version of a job description for an Urdu-speaking worker (English / Roman Urdu / mixed requests).

Lifecycle of ``JobRequest.description_ur``:
- ``suggested``: written by the interpretation call that also suggested the catalog fields (or typed/edited by the
  customer). Never shared.
- ``approved``: the customer checked it. Shared with invited workers ONLY while ``description_ur_basis`` equals the
  digest of the current ``description``.
- ``outdated``: the description (its source) changed after the Urdu version was written or approved, so it can no
  longer be shared as current. The customer edits/approves it again (or it is replaced by a new suggestion).

The original description is always kept and shared as written; an Urdu version is an addition, never a replacement.
"""

from __future__ import annotations

import hashlib
import re

from .models import JobRequest

MAX_URDU_DESCRIPTION = 800  # read aloud together with the task, area and time (speech text ≤ 1500 characters)
_ARABIC = re.compile("[؀-ۿ]")
_LATIN = re.compile("[A-Za-z]")
Status = JobRequest.UrduStatus


def basis(text: str) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()


def has_urdu_script(text: str) -> bool:
    return bool(_ARABIC.search(text or ""))


def text_language(text: str) -> str:
    """ur | en | mixed (by script): "en" also covers Roman Urdu written in Latin letters."""
    urdu, latin = len(_ARABIC.findall(text or "")), len(_LATIN.findall(text or ""))
    if urdu and latin and latin * 4 >= urdu:
        return "mixed"
    if urdu:
        return "ur"
    return "en" if latin else ""


def needs_urdu(job: JobRequest) -> bool:
    """English, Roman Urdu or mixed input: an Urdu-speaking worker benefits from an approved Urdu version."""
    source = job.original_text or job.description
    if job.source_language in ("en", "mixed"):
        return True
    return bool(source) and text_language(source) in ("en", "mixed")


def description_language(job: JobRequest) -> str:
    return text_language(job.description) or job.source_language or ""


def suggest(job: JobRequest, urdu: str | None) -> None:
    """Store an AI suggestion (not shared until the customer approves it). Never overwrites customer work."""
    urdu = (urdu or "").strip()[:MAX_URDU_DESCRIPTION]
    if not urdu or not has_urdu_script(urdu) or not needs_urdu(job):
        return
    if job.description_ur_status == Status.APPROVED and job.description_ur_basis == basis(job.description):
        return
    job.description_ur, job.description_ur_status = urdu, Status.SUGGESTED
    job.description_ur_basis = basis(job.description)


def description_changed(job: JobRequest, old_description: str) -> None:
    """The source changed: a pending or approved Urdu version can no longer be shared as current."""
    if basis(old_description) != basis(job.description) and job.description_ur_status in (Status.SUGGESTED, Status.APPROVED):
        job.description_ur_status = Status.OUTDATED


def edit(job: JobRequest, *, text: str | None = None, approved: bool | None = None) -> dict[str, list[tuple[str, str]]]:
    """Apply the customer's edit and/or approval. Returns field errors (nothing is changed when there are errors)."""
    errors: dict[str, list[tuple[str, str]]] = {}
    new_text = job.description_ur if text is None else text.strip()
    if len(new_text) > MAX_URDU_DESCRIPTION:
        errors["description_ur"] = [("max_length", f"Use at most {MAX_URDU_DESCRIPTION} characters.")]
    if approved and not new_text:
        errors["description_ur"] = [("required", "Write the Urdu description before approving it.")]
    elif approved and not has_urdu_script(new_text):
        errors["description_ur"] = [("urdu_script_required", "Write the Urdu description in Urdu script.")]
    if approved and not job.description.strip():
        errors["description"] = [("required", "Describe the job first.")]
    if errors:
        return errors
    if text is not None and " ".join(new_text.split()) != " ".join(job.description_ur.split()):
        job.description_ur = new_text
        job.description_ur_status = Status.SUGGESTED if new_text else Status.NONE  # an edit needs approval again
        job.description_ur_basis = basis(job.description) if new_text else ""
    if approved is True:
        job.description_ur_status, job.description_ur_basis = Status.APPROVED, basis(job.description)
    elif approved is False and job.description_ur_status == Status.APPROVED:
        job.description_ur_status = Status.SUGGESTED
    return errors


def effective_status(job: JobRequest) -> str:
    status = job.description_ur_status
    if status in (Status.SUGGESTED, Status.APPROVED) and job.description_ur_basis != basis(job.description):
        return Status.OUTDATED
    return status


def shareable(job: JobRequest) -> str | None:
    """The Urdu version a worker may see: approved for the CURRENT description, else None."""
    if effective_status(job) == Status.APPROVED and job.description_ur.strip():
        return job.description_ur
    return None


def payload(job: JobRequest) -> dict:
    return {
        "needed": needs_urdu(job),
        "text": job.description_ur,
        "status": effective_status(job) or "none",
        "description_language": description_language(job) or None,
    }
