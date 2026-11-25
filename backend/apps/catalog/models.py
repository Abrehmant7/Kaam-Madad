"""Service catalog (database content, not hard-coded screen logic).

- Trade → ServiceTag (specific services a worker of that trade may offer)
- City → Area (sample service areas; coverage is not limited to a fixed list)
- SpecialityQuestion: the three worker questions; their choices are the trade's
  service tags, so the questions share one relationship instead of three
  disconnected label lists.

Every entry has a stable ``code`` (never reused, referenced by later modules),
Urdu and English labels, and an active flag. Deactivate entries rather than
deleting them; foreign keys use PROTECT.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .icons import ICON_CHOICES

code_validator = RegexValidator(
    r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$",
    message=_("Use lowercase letters, digits, '-' or '_' (e.g. elec_fan_install)."),
    code="invalid_code",
)


class CatalogEntry(models.Model):
    code = models.CharField(
        max_length=64,
        unique=True,
        validators=[code_validator],
        help_text=_("Stable identifier. Do not change or reuse once in use."),
    )
    label_ur = models.CharField(_("Urdu label"), max_length=120)
    label_en = models.CharField(_("English label"), max_length=120)
    is_active = models.BooleanField(default=True, help_text=_("Inactive entries are hidden from the app."))
    sort_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return f"{self.label_en} ({self.code})"


class Trade(CatalogEntry):
    icon = models.CharField(max_length=32, choices=ICON_CHOICES)

    class Meta(CatalogEntry.Meta):
        verbose_name = _("trade")


class ServiceTag(CatalogEntry):
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="services")
    icon = models.CharField(max_length=32, choices=ICON_CHOICES, blank=True, default="")

    class Meta(CatalogEntry.Meta):
        verbose_name = _("service tag")
        ordering = ["trade__sort_order", "sort_order", "code"]


class City(CatalogEntry):
    class Meta(CatalogEntry.Meta):
        verbose_name = _("city")
        verbose_name_plural = _("cities")


class Area(CatalogEntry):
    class Kind(models.TextChoices):
        SECTOR = "sector", _("Sector")
        LOCALITY = "locality", _("Locality / neighbourhood")

    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="areas")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.LOCALITY)
    # Approximate public centre point, for "approximate distance" in later modules.
    # Left empty until verified; never a person's location.
    centre_latitude = models.DecimalField(
        max_digits=8, decimal_places=5, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    centre_longitude = models.DecimalField(
        max_digits=8, decimal_places=5, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    class Meta(CatalogEntry.Meta):
        verbose_name = _("area")
        ordering = ["city__sort_order", "sort_order", "code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(centre_latitude__isnull=True, centre_longitude__isnull=True)
                | Q(centre_latitude__isnull=False, centre_longitude__isnull=False),
                name="catalog_area_centre_both_or_neither",
            ),
        ]


class SpecialityQuestion(models.Model):
    """One of the guided worker questions (WK-02). Prompts may contain ``{trade}``."""

    class ChoiceSource(models.TextChoices):
        TRADE_SERVICES = "trade_services", _("All active services of the trade")
        SERVICES_OFFERED = "services_offered", _("Services selected in the 'services offered' question")

    code = models.CharField(max_length=64, unique=True, validators=[code_validator])
    prompt_ur = models.CharField(max_length=200)
    prompt_en = models.CharField(max_length=200)
    help_ur = models.CharField(max_length=300, blank=True, default="")
    help_en = models.CharField(max_length=300, blank=True, default="")
    choice_source = models.CharField(max_length=32, choices=ChoiceSource.choices)
    min_selections = models.PositiveSmallIntegerField(default=0)
    max_selections = models.PositiveSmallIntegerField(null=True, blank=True, help_text=_("Empty = no maximum."))
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_selections__isnull=True) | Q(max_selections__gte=models.F("min_selections")),
                name="catalog_question_max_gte_min",
            ),
        ]

    def __str__(self) -> str:
        return self.code
