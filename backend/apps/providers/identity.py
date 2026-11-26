"""CNIC OCR and identity-verification provider boundaries (ID-01, ID-02).

OCR (ID-01) — selected by settings.CNIC_OCR_PROVIDER:
- "tesseract": the Tesseract executable installed on the Django host (``TESSERACT_CMD``: a full
  path, or a name found on PATH; ``TESSERACT_LANG``, default ``eng``). The image is decoded and
  normalised with Pillow (EXIF orientation, grayscale, size, contrast), written to a private
  temporary folder, read by Tesseract with a bounded time budget (``OCR_TIMEOUT_SECONDS``), and
  the folder is deleted. If no 13-digit number is found, the image is retried rotated by 90°,
  270° and 180° while time remains. No external OCR service is called.
- "unconfigured": ProviderNotConfigured.

Only two fields are extracted: the printed English name (from the labelled "Name" field) and
the 13-digit identity number. A missing or ambiguous field is returned as None. Raw OCR text
never leaves this module: it is not logged, stored or returned. OCR success never changes
identity status — the worker reviews/corrects both fields, then the registry check decides.

Identity verification (ID-02) — ``IdentityVerificationProvider`` takes CONFIRMED details.
Implementations live in apps.workers.identity (the demo registry is database content).
Authorised NADRA access does not exist yet; nothing may be labelled "NADRA verified".
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .errors import ProviderInvalidOutput, ProviderNotConfigured, ProviderUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CnicOcrResult:
    name: str | None
    cnic_number: str | None  # 13 digits, no dashes
    provider: str = ""
    engine: str = ""
    rotation: int = 0  # degrees the image was turned for the successful read
    simulated: bool = False

    @property
    def status(self) -> str:
        if self.name and self.cnic_number:
            return "read"
        return "partial" if (self.name or self.cnic_number) else "unreadable"


@dataclass(frozen=True)
class IdentityVerificationResult:
    outcome: str  # "verified" | "name_mismatch" | "no_record" | "needs_review"
    provider_reference: str
    method: str  # exact method shown to users and staff, e.g. "demo_registry"
    provider: str
    simulated: bool = False
    extra: dict = field(default_factory=dict)


class CnicOcrProvider(ABC):
    name: str
    simulated: bool = False

    @abstractmethod
    def extract(self, *, image: bytes, mime_type: str) -> CnicOcrResult: ...


class IdentityVerificationProvider(ABC):
    name: str
    simulated: bool = False

    @abstractmethod
    def verify(self, *, confirmed_fields: dict[str, str], consent_reference: str) -> IdentityVerificationResult: ...


# --- Parsing printed card text (pure functions, unit-tested) ---------------------------------

# 12345-1234567-1 with optional spaces/dashes, or 13 digits in a row. OCR often reads 0 as O/o.
_NUMBER = re.compile(r"(?<![\dA-Za-z])([\dOo]{5})\s*[-–—~_.]?\s*([\dOo]{7})\s*[-–—~_.]?\s*([\dOo])(?![\dA-Za-z])")
_NAME_LABEL = re.compile(r"^(?P<prefix>.*?)\bname\b\s*[:;.\-|]*\s*(?P<rest>.*)$", re.IGNORECASE)
_NOT_HOLDER = re.compile(r"\b(father|husband|guardian)\b", re.IGNORECASE)
_NAME_VALUE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,58}[A-Za-z.]$")
_LABEL_WORDS = re.compile(r"\b(identity|number|gender|country|date|birth|issue|expiry|valid|card|demo)\b", re.IGNORECASE)


def find_cnic_numbers(text: str) -> set[str]:
    """Distinct 13-digit candidates in the text (dashes/spaces removed, O read as 0)."""
    found = set()
    for match in _NUMBER.finditer(text):
        digits = "".join(match.groups()).replace("O", "0").replace("o", "0")
        if digits.isdigit() and len(digits) == 13:
            found.add(digits)
    return found


def extract_number(text: str) -> str | None:
    """The number only when exactly one valid candidate exists; ambiguity gives None."""
    candidates = find_cnic_numbers(text)
    return next(iter(candidates)) if len(candidates) == 1 else None


def _clean_name(value: str) -> str | None:
    value = re.sub(r"[|_“”\"`]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .:-'")
    if not value or any(ch.isdigit() for ch in value) or _LABEL_WORDS.search(value):
        return None
    return value if _NAME_VALUE.match(value) else None


def extract_name(text: str) -> str | None:
    """The value of the holder's "Name" field: after the label, or on the next line.

    "Father Name" / "Husband Name" are skipped. Several different names → None (ambiguous).
    """
    lines = [line.strip() for line in text.splitlines()]
    names: list[str] = []
    for index, line in enumerate(lines):
        match = _NAME_LABEL.match(line)
        if not match or _NOT_HOLDER.search(match.group("prefix")):
            continue
        candidate = _clean_name(match.group("rest"))
        if candidate is None:
            following = next((nxt for nxt in lines[index + 1:index + 3] if nxt), "")
            candidate = _clean_name(following)
        if candidate:
            names.append(candidate)
    distinct = {name.casefold() for name in names}
    return names[0] if len(distinct) == 1 else None


# --- Tesseract -------------------------------------------------------------------------------------

_RESOLVED: dict[tuple[str, str], tuple[str, str]] = {}  # (cmd, lang) → (executable, version)
WINDOWS_DEFAULT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def resolve_tesseract() -> tuple[str, str]:
    """Executable path and version, or ProviderNotConfigured with a setup reason."""
    cmd, lang = settings.TESSERACT_CMD or "tesseract", settings.TESSERACT_LANG or "eng"
    if (cmd, lang) in _RESOLVED:
        return _RESOLVED[(cmd, lang)]
    path = Path(cmd)
    executable = str(path) if path.is_file() else shutil.which(cmd)
    if not executable and cmd == "tesseract" and WINDOWS_DEFAULT.is_file():
        executable = str(WINDOWS_DEFAULT)  # standard location of the Windows installer
    if not executable:
        raise ProviderNotConfigured("tesseract_not_found")
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
        langs = subprocess.run([executable, "--list-langs"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        raise ProviderNotConfigured("tesseract_not_runnable") from None
    available = {line.strip() for line in (langs.stdout + langs.stderr).splitlines()}
    if any(code not in available for code in lang.split("+")):
        raise ProviderNotConfigured("tesseract_language_missing")
    first_line = (version.stdout or version.stderr).splitlines()[0] if (version.stdout or version.stderr) else "tesseract"
    _RESOLVED[(cmd, lang)] = (executable, first_line.strip()[:64])
    return _RESOLVED[(cmd, lang)]


def prepare_image(image: bytes, rotation: int = 0):
    """Decode and normalise for OCR: EXIF orientation, grayscale, ~1800 px wide, autocontrast."""
    from PIL import Image, ImageFilter, ImageOps

    with Image.open(io.BytesIO(image)) as opened:
        picture = ImageOps.exif_transpose(opened).convert("L")
    if rotation:
        picture = picture.rotate(rotation, expand=True)
    width, height = picture.size
    scale = 1800 / max(width, 1)
    if scale > 1.15 or scale < 0.85:
        picture = picture.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
    picture = ImageOps.autocontrast(picture, cutoff=1)
    return picture.filter(ImageFilter.SHARPEN)


def _rank(result: CnicOcrResult) -> tuple[int, int]:
    """Prefer both fields, then one field (the number first), then nothing."""
    return ({"read": 2, "partial": 1}.get(result.status, 0), int(result.cnic_number is not None))


class TesseractCnicOcr(CnicOcrProvider):
    name = "tesseract"
    ROTATIONS = (0, 90, 270, 180)

    def __init__(self):
        self.executable, self.version = resolve_tesseract()
        self.lang = settings.TESSERACT_LANG or "eng"

    def _run(self, path: Path, timeout: float) -> str:
        try:
            completed = subprocess.run(
                [self.executable, str(path), "stdout", "-l", self.lang, "--psm", "6"],
                capture_output=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            raise ProviderUnavailable("ocr_timeout") from None
        except OSError:
            raise ProviderNotConfigured("tesseract_not_runnable") from None
        if completed.returncode != 0:
            # stderr may echo image details; log only the exit code.
            logger.warning("Tesseract exited with code %s.", completed.returncode)
            raise ProviderUnavailable("ocr_engine_error")
        return completed.stdout.decode("utf-8", "replace")

    def extract(self, *, image: bytes, mime_type: str) -> CnicOcrResult:
        deadline = time.monotonic() + settings.OCR_TIMEOUT_SECONDS
        best: CnicOcrResult | None = None
        with tempfile.TemporaryDirectory(prefix="kaam-madad-ocr-") as folder:  # deleted on exit
            for rotation in self.ROTATIONS:
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    break
                try:
                    prepared = prepare_image(image, rotation)
                except Exception:  # noqa: BLE001 — Pillow raises many types for broken files
                    raise ProviderInvalidOutput("image_not_decodable") from None
                path = Path(folder) / f"scan-{rotation}.png"
                prepared.save(path, format="PNG")
                try:
                    text = self._run(path, timeout=remaining)
                finally:
                    path.unlink(missing_ok=True)
                result = CnicOcrResult(
                    name=extract_name(text), cnic_number=extract_number(text), provider=self.name,
                    engine=self.version, rotation=rotation,
                )
                del text  # raw OCR text is never kept
                if best is None or _rank(result) > _rank(best):
                    best = result
                if result.status == "read":
                    break
        if best is None:
            raise ProviderUnavailable("ocr_timeout")
        return best


class UnconfiguredCnicOcr(CnicOcrProvider):
    name = "unconfigured"

    def extract(self, **kwargs) -> CnicOcrResult:
        raise ProviderNotConfigured("no_ocr_provider_selected")


class UnconfiguredIdentityVerification(IdentityVerificationProvider):
    name = "unconfigured"

    def verify(self, **kwargs) -> IdentityVerificationResult:
        raise ProviderNotConfigured("no_authorised_identity_provider")
