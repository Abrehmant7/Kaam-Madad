"""Server-side role permissions (AUTH-01). Frontend route guards are convenience only."""

from rest_framework.permissions import BasePermission

from .models import User


class IsMarketplaceUser(BasePermission):
    """An active, signed-in worker or customer."""

    message = "This action is only available to worker and customer accounts."
    code = "marketplace_role_required"

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role in (User.Role.WORKER, User.Role.CUSTOMER)
        )


class IsWorker(IsMarketplaceUser):
    message = "This action is only available to worker accounts."
    code = "worker_role_required"

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.user.role == User.Role.WORKER


class IsCustomer(IsMarketplaceUser):
    message = "This action is only available to customer accounts."
    code = "customer_role_required"

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.user.role == User.Role.CUSTOMER
