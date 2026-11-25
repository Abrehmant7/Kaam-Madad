from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("me/language/", views.LanguagePreferenceView.as_view(), name="auth-language"),
    path("phone-confirmation/", views.PhoneConfirmationView.as_view(), name="auth-phone-confirmation"),
    path(
        "phone-confirmation/verify/",
        views.PhoneConfirmationVerifyView.as_view(),
        name="auth-phone-confirmation-verify",
    ),
]
