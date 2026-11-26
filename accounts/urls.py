from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    OrganiserRegisterView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PhoneVerificationView,
    RegisterView,
    account_settings,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("register/organiser/", OrganiserRegisterView.as_view(), name="register-organiser"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("settings/", account_settings, name="account-settings"),
    path("phone/verify/", PhoneVerificationView.as_view(), name="phone-verify"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
