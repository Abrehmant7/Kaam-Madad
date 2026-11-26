"""Load the fictional demo identity registry. Idempotent; refuses to run in a live deployment.

    python manage.py seed_demo_registry
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.workers.demo_registry_data import DEMO_RECORDS
from apps.workers.identity import cnic_digest, demo_mode, mask_cnic
from apps.workers.models import DemoIdentityRecord


class Command(BaseCommand):
    help = "Create or update the fictional demo identity registry (demo deployments only)."

    def handle(self, *args, **options):
        if not demo_mode():
            raise CommandError(
                f"APP_DEPLOYMENT_MODE={settings.DEPLOYMENT_MODE}: demo identity records are only allowed in a demo deployment."
            )
        created = updated = 0
        for record in DEMO_RECORDS:
            _, was_created = DemoIdentityRecord.objects.update_or_create(
                reference=record["reference"],
                defaults={
                    "full_name_en": record["full_name_en"],
                    "full_name_ur": record["full_name_ur"],
                    "demo_address": record["demo_address"],
                    # Recomputed every run, so re-seeding after a SECRET_KEY change keeps matches working.
                    "cnic_digest": cnic_digest(record["cnic"]),
                    "cnic_masked": mask_cnic(record["cnic"]),
                    "is_active": True,
                },
            )
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(
            f"Demo identity registry: {created} created, {updated} updated ({len(DEMO_RECORDS)} fictional records)."
        ))
