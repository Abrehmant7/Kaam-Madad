"""CNIC OCR and identity-verification provider BOUNDARIES (ID-01, ID-02) — interfaces only.

M3 defines these separate boundaries but exposes no endpoints and accepts no CNIC
uploads. M4 (worker onboarding) handoff:

OCR (ID-01)
- Implement ``CnicOcrProvider.extract`` for a chosen OCR/vision provider. Input: the
  private CNIC image bytes and MIME type (stored like private audio, never as a
  message attachment or public asset; never logged). Output: ``CnicOcrResult`` with
  draft fields (name, CNIC number, expiry) each marked present/uncertain.
- OCR success never changes identity status. The worker confirms/corrects fields;
  format checks (13-digit CNIC, plausible expiry) are deterministic code.

Identity verification (ID-02, ID-03)
- ``IdentityVerificationProvider.verify`` takes CONFIRMED details plus the worker's
  consent record and returns a provider reference and outcome.
- Real NADRA verification may only be implemented with authorised institutional
  access and a signed contract. Until then the only implementation is
  ``UnconfiguredIdentityVerification``; staff manual review and demo approval are
  separate, clearly labelled methods in M4 — never labelled "NADRA verified".
- A missing or failing provider must never produce a verified result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .errors import ProviderNotConfigured


@dataclass(frozen=True)
class CnicOcrResult:
    fields: dict[str, str | None]
    uncertain: list[str] = field(default_factory=list)
    provider: str = ""
    simulated: bool = False


@dataclass(frozen=True)
class IdentityVerificationResult:
    outcome: str  # "verified" | "not_verified" | "needs_review"
    provider_reference: str
    method: str  # exact method label shown to users/staff, e.g. "nadra_verisys"
    provider: str


class CnicOcrProvider(ABC):
    name: str

    @abstractmethod
    def extract(self, *, image: bytes, mime_type: str) -> CnicOcrResult: ...


class IdentityVerificationProvider(ABC):
    name: str

    @abstractmethod
    def verify(self, *, confirmed_fields: dict[str, str], consent_reference: str) -> IdentityVerificationResult: ...


class UnconfiguredCnicOcr(CnicOcrProvider):
    name = "unconfigured"

    def extract(self, **kwargs) -> CnicOcrResult:
        raise ProviderNotConfigured("ocr_not_implemented_until_m4")


class UnconfiguredIdentityVerification(IdentityVerificationProvider):
    name = "unconfigured"

    def verify(self, **kwargs) -> IdentityVerificationResult:
        raise ProviderNotConfigured("no_authorised_identity_provider")
