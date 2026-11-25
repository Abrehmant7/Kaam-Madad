"""Load or refresh the initial catalog. Safe to run repeatedly.

- Matches records by stable ``code``; creates missing ones, updates changed
  labels/icons/ordering/relationships of known ones.
- Never deletes anything and never touches records with other codes
  (staff-created entries are left alone).
- Keeps an existing record's ``is_active`` value, so a staff deactivation survives re-seeding.
- Touches only catalog tables: no users, credentials, or identity data.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog import seed_data
from apps.catalog.models import Area, City, ServiceTag, SpecialityQuestion, Trade


class Command(BaseCommand):
    help = "Create or update the initial trades, service tags, cities/areas and speciality questions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without saving them.")

    def handle(self, *args, dry_run: bool = False, **options):
        self.stats: dict[str, Counter] = {}
        with transaction.atomic():
            trades = {row["code"]: self._upsert(Trade, row) for row in seed_data.TRADES}
            for trade_code, rows in seed_data.SERVICE_TAGS.items():
                for order, (code, label_en, label_ur, icon) in enumerate(rows, start=1):
                    self._upsert(
                        ServiceTag,
                        {
                            "code": code,
                            "label_en": label_en,
                            "label_ur": label_ur,
                            "icon": icon,
                            "trade": trades[trade_code],
                            "sort_order": order * 10,
                        },
                    )
            cities = {row["code"]: self._upsert(City, row) for row in seed_data.CITIES}
            for city_code, rows in seed_data.AREAS.items():
                for order, (code, label_en, label_ur, kind) in enumerate(rows, start=1):
                    self._upsert(
                        Area,
                        {
                            "code": code,
                            "label_en": label_en,
                            "label_ur": label_ur,
                            "kind": kind,
                            "city": cities[city_code],
                            "sort_order": order * 10,
                        },
                    )
            for row in seed_data.SPECIALITY_QUESTIONS:
                self._upsert(SpecialityQuestion, row)
            if dry_run:
                transaction.set_rollback(True)

        prefix = "[dry run] " if dry_run else ""
        for model_name, counts in self.stats.items():
            self.stdout.write(
                f"{prefix}{model_name}: {counts['created']} created, "
                f"{counts['updated']} updated, {counts['unchanged']} unchanged"
            )
        self.stdout.write(self.style.SUCCESS(f"{prefix}Catalog seed complete."))

    def _upsert(self, model, values: dict):
        values = dict(values)
        code = values.pop("code")
        counts = self.stats.setdefault(model._meta.verbose_name_plural.capitalize(), Counter())
        instance = model.objects.filter(code=code).first()
        if instance is None:
            instance = model.objects.create(code=code, **values)
            counts["created"] += 1
            return instance
        changed = [field for field, value in values.items() if getattr(instance, field) != value]
        if changed:
            for field in changed:
                setattr(instance, field, values[field])
            instance.save(update_fields=[*changed, "updated_at"])
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        return instance
