import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Area, City, ServiceTag, Trade
from apps.jobs.models import JobRequest
from apps.workers.models import IdentityVerification, WorkerProfile

User = get_user_model()
PASSWORD = "Strong-Pass-2026!"
KARACHI = ZoneInfo("Asia/Karachi")
_phone = iter(range(1_000_000, 9_999_999))


def next_phone() -> str:
    return f"0301{next(_phone)}"


def seed() -> None:
    with open(Path(tempfile.gettempdir()) / "seed-m6.log", "w") as log:
        call_command("seed_catalog", stdout=log)


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def make_worker(*, trade="electrician", offered=("elec_fan_install", "elec_wiring_repair"), primary=("elec_fan_install",),
                excluded=(), city="islamabad", areas=("isb-g-9",), accepting=True, identity="demo_approved", active=True):
    """A fictional worker with a complete profile (validity is still re-checked by eligibility)."""
    user = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.WORKER, is_demo=True, is_active=active)
    profile = WorkerProfile.objects.create(user=user, trade=Trade.objects.get(code=trade), city=City.objects.get(code=city),
                                           accepting_requests=accepting)
    profile.services_offered.set(ServiceTag.objects.filter(code__in=offered))
    profile.primary_specialities.set(ServiceTag.objects.filter(code__in=primary))
    profile.services_not_offered.set(ServiceTag.objects.filter(code__in=excluded))
    profile.service_areas.set(Area.objects.filter(code__in=areas))
    if identity:
        now = timezone.now()
        IdentityVerification.objects.create(
            user=user, consent_given_at=now, consent_version="test", status=identity,
            method="demo_registry" if identity == "demo_approved" else "",
            decided_at=now if identity == "demo_approved" else None, cnic_masked="*****-*****67-1",
            registry_reference="DEMO-REG-0001",
        )
    return profile


def make_confirmed_job(customer, *, trade="electrician", services=("elec_fan_install",), area="isb-g-9",
                       description="Two ceiling fans to install.", address="House 5, Street 9", access="Ring twice"):
    area_obj = Area.objects.select_related("city").get(code=area)
    start = (timezone.now() + timedelta(days=1)).astimezone(KARACHI).replace(hour=17, minute=0, second=0, microsecond=0)
    job = JobRequest.objects.create(
        customer=customer, status=JobRequest.Status.CONFIRMED, source_kind="text", source_language="en",
        original_text="secret original words", description=description, trade=Trade.objects.get(code=trade),
        city=area_obj.city, area=area_obj, window_start=start, window_end=start + timedelta(hours=2),
        address_private=address, access_notes=access, confirmed_at=timezone.now(),
    )
    job.services.set(ServiceTag.objects.filter(code__in=services))
    return job


def karachi(dt: datetime) -> datetime:
    return dt.astimezone(KARACHI)
