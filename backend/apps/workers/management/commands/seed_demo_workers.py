"""Create FICTIONAL demo workers for rehearsing recommendations and invitations (demo mode only).

    python manage.py seed_demo_workers

Idempotent: re-running resets these accounts to the profiles below. Every account is marked
``is_demo``; identity is "demo approved" against the fictional demo registry (seed_demo_registry),
which only counts in a demo deployment. Phone numbers are login identifiers only (no SMS is sent).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Area, City, ServiceTag, Trade
from apps.workers.identity import demo_mode
from apps.workers.models import IdentityVerification, WorkerProfile

PASSWORD = "Demo-Worker-2026"
DEMO_WORKERS = [
    # phone, trade, offered, main speciality, areas, accepting, registry reference
    ("03009990101", "electrician", ["elec_fan_install", "elec_wiring_repair", "elec_light_fitting"], "elec_fan_install",
     ["isb-g-9", "isb-g-10", "isb-f-8"], True, "DEMO-REG-0001"),
    ("03009990102", "electrician", ["elec_fan_install", "elec_switch_socket"], "elec_switch_socket",
     ["isb-g-9", "isb-i-8"], True, "DEMO-REG-0002"),
    ("03009990103", "plumber", ["plmb_leak_repair", "plmb_tap_shower", "plmb_geyser"], "plmb_leak_repair",
     ["isb-g-10", "rwp-saddar"], True, "DEMO-REG-0003"),
    ("03009990104", "electrician", ["elec_fan_install", "elec_wiring_repair"], "elec_fan_install",
     ["isb-g-9"], False, "DEMO-REG-0001"),  # paused: never recommended
]


class Command(BaseCommand):
    help = "Create or reset fictional demo workers (demo deployments only)."

    def handle(self, *args, **options):
        if not demo_mode():
            raise CommandError("Demo workers are only allowed when APP_DEPLOYMENT_MODE=demo.")
        with transaction.atomic():
            for phone, trade, offered, main, areas, accepting, reference in DEMO_WORKERS:
                user = User.objects.filter(phone_number=f"+92{phone[1:]}").first()
                if user is None:
                    user = User.objects.create_user(phone, PASSWORD, role=User.Role.WORKER, is_demo=True)
                elif user.role != User.Role.WORKER:
                    raise CommandError(f"{phone} exists with another role; not changed.")
                else:
                    user.set_password(PASSWORD)
                    user.is_active, user.is_demo = True, True
                    user.save()
                area_objs = list(Area.objects.filter(code__in=areas))
                profile, _ = WorkerProfile.objects.get_or_create(user=user)
                profile.trade = Trade.objects.get(code=trade)
                profile.city = City.objects.get(pk=area_objs[0].city_id)
                profile.accepting_requests = accepting
                profile.work_saved_at = profile.areas_saved_at = timezone.now()
                profile.save()
                profile.services_offered.set(ServiceTag.objects.filter(code__in=offered))
                profile.primary_specialities.set(ServiceTag.objects.filter(code=main))
                profile.services_not_offered.clear()
                profile.service_areas.set(area_objs)
                IdentityVerification.objects.filter(user=user).exclude(status="superseded").update(status="superseded")
                now = timezone.now()
                IdentityVerification.objects.create(
                    user=user, consent_given_at=now, consent_version="demo-seed", status="demo_approved",
                    method="demo_registry", decided_at=now, registry_outcome="match", registry_provider="demo_registry",
                    registry_simulated=True, registry_reference=reference, cnic_masked="*****-*****00-0",
                )
        self.stdout.write(self.style.SUCCESS(
            f"{len(DEMO_WORKERS)} fictional demo workers ready (password {PASSWORD}): "
            + ", ".join(phone for phone, *_ in DEMO_WORKERS)
        ))
