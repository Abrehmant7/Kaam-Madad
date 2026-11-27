"""Review API (M9). Contracts: docs/api.md § Completion, disputes and reviews."""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsWorker
from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.bookings.models import Booking
from apps.workers.models import WorkerProfile

from . import services


class ReviewThrottle(ConfigurableRateThrottle):
    scope = "review_user"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class ReviewSerializer(StrictFieldsMixin, serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, default="", max_length=500, trim_whitespace=True)
    audio_clip_id = serializers.UUIDField(required=False)
    transcription_id = serializers.UUIDField(required=False)


@method_decorator(never_cache, name="dispatch")
class ReviewView(APIView):
    """POST /bookings/{id}/review/ — the customer's one review after confirming completion."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReviewThrottle]

    def post(self, request, booking_id):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review, created = services.submit_review(request.user, booking_id, **serializer.validated_data)
        return Response({**services.review_payload(review, "customer"), "created": created},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@method_decorator(never_cache, name="dispatch")
class WorkerFeedbackView(APIView):
    """GET /bookings/feedback/ — the signed-in worker's completed jobs, rating and visible job feedback."""

    permission_classes = [IsWorker]

    def get(self, request):
        profile = WorkerProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response({"completed_jobs": 0, "review_count": 0, "average_rating": None, "jobs": []})
        stats = services.worker_stats([profile.pk])[str(profile.pk)]
        completed = (Booking.objects.filter(worker_profile=profile, status=Booking.Status.COMPLETED)
                     .select_related("invitation").prefetch_related("completed_services", "reviews").order_by("-completed_at")[:50])
        jobs = []
        for booking in completed:
            review = next((r for r in booking.reviews.all() if r.hidden_at is None), None)
            summary = booking.invitation.shared_summary
            jobs.append({
                "booking_id": str(booking.id), "completed_at": booking.completed_at.isoformat().replace("+00:00", "Z"),
                "trade": summary.get("trade"), "area": summary.get("area"),  # area only: never the address
                "services": sorted(s.code for s in booking.completed_services.all()),
                "review": services.review_payload(review, "worker") if review else None,
            })
        return Response({**{k: v for k, v in stats.as_dict().items() if k != "relevant_jobs"}, "jobs": jobs})
