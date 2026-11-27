"""Prototype evidence retention (M10, SEC-03): remove evidence CONTENT of long-closed reports.

    python manage.py purge_report_evidence [--days 180] [--dry-run]

Rules:
- Only reports that are resolved or dismissed, and closed more than ``--days`` ago
  (default ``REPORT_EVIDENCE_RETENTION_DAYS``).
- Never while the report is open or reviewing, and never while its booking is awaiting completion or disputed
  (evidence of open cases and active disputes is preserved).
- Removes the image file or the audio recording; the report, its text, decisions and an evidence record marked
  "removed" stay for the audit trail. Prints counts only — no names, text or file paths.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.reports.models import Report, ReportEvidence


class Command(BaseCommand):
    help = "Remove evidence content of reports closed longer than the retention period."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=settings.REPORT_EVIDENCE_RETENTION_DAYS)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, days, dry_run, **options):
        cutoff = timezone.now() - timedelta(days=days)
        due = (ReportEvidence.objects.filter(deleted_at__isnull=True, report__status__in=Report.CLOSED, report__closed_at__lt=cutoff)
               .exclude(report__booking__status__in=[Booking.Status.COMPLETION_REQUESTED, Booking.Status.DISPUTED])
               .select_related("audio_clip"))
        count = 0
        for item in due:
            count += 1
            if dry_run:
                continue
            with transaction.atomic():
                if item.kind == ReportEvidence.Kind.IMAGE and item.file:
                    item.file.delete(save=False)
                clip = item.audio_clip
                if clip is not None:
                    clip.file.delete(save=False)
                    item.audio_clip = None
                item.deleted_at = timezone.now()
                item.save(update_fields=["file", "audio_clip", "deleted_at"])
                if clip is not None:
                    clip.delete()
        verb = "would remove" if dry_run else "removed"
        self.stdout.write(f"Evidence items {verb}: {count} (reports closed before {cutoff:%Y-%m-%d}).")
