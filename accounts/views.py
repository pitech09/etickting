from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import login, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views import View

from organisations.forms import OrganisationForm
from organisations.models import OrganisationMembership

from .forms import AccountDetailsForm, OrganiserRegistrationForm, RegistrationForm
from .models import User
from .services import find_verified_phone_user, issue_otp, normalize_phone, verify_otp


def get_post_login_redirect(user):
    if user.is_staff or user.is_superuser:
        return reverse("admin:index")
    if user.organisation_memberships.exists():
        return reverse("dashboard")
    return reverse("public-event-list")


class RegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request):
        return render(request, self.template_name, {"form": RegistrationForm()})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    issue_otp(
                        user=user,
                        phone=user.phone_number,
                        purpose="phone_verification",
                        ip_address=request.META.get("REMOTE_ADDR", ""),
                    )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                request.session["pending_phone_verification_user_id"] = str(user.pk)
                messages.success(request, "Your account was created. Verify your phone number to continue.")
                return redirect("phone-verify")
        return render(request, self.template_name, {"form": form})


class OrganiserRegisterView(View):
    template_name = "accounts/register_organiser.html"

    def get(self, request):
        return render(request, self.template_name, {"form": OrganiserRegistrationForm()})

    def post(self, request):
        form = OrganiserRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    organisation_form = OrganisationForm({
                        "name": form.cleaned_data["organisation_name"],
                        "description": form.cleaned_data["organisation_description"],
                    })
                    organisation = organisation_form.save()
                    OrganisationMembership.objects.create(
                        organisation=organisation,
                        user=user,
                        role=OrganisationMembership.Role.OWNER,
                    )
                    issue_otp(
                        user=user,
                        phone=user.phone_number,
                        purpose="phone_verification",
                        ip_address=request.META.get("REMOTE_ADDR", ""),
                    )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                request.session["pending_phone_verification_user_id"] = str(user.pk)
                messages.success(request, "Your account was created. Verify your phone number to continue.")
                return redirect("phone-verify")
        return render(request, self.template_name, {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = False

    def form_valid(self, form):
        user = form.get_user()
        if not user.phone_verified_at:
            try:
                issue_otp(
                    user=user,
                    phone=user.phone_number,
                    purpose="phone_verification",
                    ip_address=self.request.META.get("REMOTE_ADDR", ""),
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
                return self.form_invalid(form)
            self.request.session["pending_phone_verification_user_id"] = str(user.pk)
            next_url = self.get_redirect_url()
            if next_url and url_has_allowed_host_and_scheme(next_url, {self.request.get_host()}):
                self.request.session["pending_phone_verification_next"] = next_url
            messages.info(self.request, "Verify your phone number before signing in. A new code was sent by SMS.")
            return redirect("phone-verify")
        return super().form_valid(form)

    def get_success_url(self):
        if self.get_redirect_url():
            return super().get_success_url()
        return get_post_login_redirect(self.request.user)


class LogoutView(auth_views.LogoutView):
    next_page = "login"


@login_required
def account_settings(request):
    current_phone = request.user.phone_number
    details_form = AccountDetailsForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Your password was updated. You are still signed in.")
                return redirect("account-settings")
        else:
            details_form = AccountDetailsForm(request.POST, instance=request.user)
            if details_form.is_valid():
                user = details_form.save(commit=False)
                if user.phone_number != current_phone:
                    try:
                        with transaction.atomic():
                            user.phone_verified_at = None
                            user.save(update_fields=["first_name", "last_name", "email", "phone_number", "phone_verified_at"])
                            issue_otp(
                                user=user,
                                phone=user.phone_number,
                                purpose="phone_verification",
                                ip_address=request.META.get("REMOTE_ADDR", ""),
                            )
                    except ValueError as exc:
                        details_form.add_error("phone_number", str(exc))
                        return render(request, "accounts/settings.html", {
                            "details_form": details_form,
                            "password_form": password_form,
                        })
                    messages.success(request, "Your details were saved. Enter the SMS code to verify your new phone number.")
                    return redirect("phone-verify")
                user.save(update_fields=["first_name", "last_name", "email", "phone_number", "phone_verified_at"])
                messages.success(request, "Your personal details were saved.")
                return redirect("account-settings")
    return render(request, "accounts/settings.html", {
        "details_form": details_form,
        "password_form": password_form,
    })


class PhoneVerificationView(View):
    template_name = "accounts/phone_verification.html"

    def get_user(self, request):
        if request.user.is_authenticated:
            return request.user
        user_id = request.session.get("pending_phone_verification_user_id")
        if not user_id:
            return None
        return User.objects.filter(pk=user_id, is_active=True).first()

    def get(self, request):
        user = self.get_user(request)
        if not user:
            return redirect("login")
        return render(request, self.template_name, {"phone": user.phone_number or ""})

    def post(self, request):
        user = self.get_user(request)
        if not user:
            return redirect("login")
        phone = request.POST.get("phone", "")
        code = request.POST.get("code", "").strip()
        if code:
            if verify_otp(user=user, code=code, purpose="phone_verification", phone=user.phone_number):
                user.phone_verified_at = timezone.now()
                user.save(update_fields=["phone_verified_at"])
                messages.success(request, "Your phone number has been verified.")
                if not request.user.is_authenticated:
                    login(request, user)
                    next_url = request.session.pop("pending_phone_verification_next", "")
                    request.session.pop("pending_phone_verification_user_id", None)
                    return redirect(next_url or get_post_login_redirect(user))
                return redirect("account-settings")
            messages.error(request, "That code is invalid or expired.")
        else:
            try:
                phone = normalize_phone(phone)
                if User.objects.filter(phone_number=phone).exclude(pk=user.pk).exists():
                    raise ValueError("That phone number is already in use.")
                with transaction.atomic():
                    user.phone_number = phone
                    user.phone_verified_at = None
                    user.save(update_fields=["phone_number", "phone_verified_at"])
                    issue_otp(user=user, phone=phone, purpose="phone_verification", ip_address=request.META.get("REMOTE_ADDR", ""))
                messages.success(request, "A verification code was sent by SMS.")
            except ValueError as exc:
                messages.error(request, str(exc))
        return render(request, self.template_name, {"phone": phone})


class PasswordResetRequestView(View):
    template_name = "accounts/password_reset_request.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        user = find_verified_phone_user(request.POST.get("phone", ""))
        if user:
            try:
                issue_otp(user=user, phone=user.phone_number, purpose="password_reset", ip_address=request.META.get("REMOTE_ADDR", ""))
            except ValueError:
                pass
        request.session["password_reset_phone"] = request.POST.get("phone", "")
        messages.info(request, "If that verified number is registered, a reset code has been sent by SMS.")
        return redirect("password-reset-confirm")


class PasswordResetConfirmView(View):
    template_name = "accounts/password_reset_confirm.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        phone = request.session.get("password_reset_phone", "")
        user = find_verified_phone_user(phone)
        if not user or not verify_otp(user=user, code=request.POST.get("code"), purpose="password_reset"):
            messages.error(request, "That code is invalid or expired.")
            return render(request, self.template_name)
        password = request.POST.get("new_password1", "")
        confirmation = request.POST.get("new_password2", "")
        try:
            validate_password(password, user)
        except Exception:
            messages.error(request, "Choose a stronger password.")
            return render(request, self.template_name)
        if password != confirmation:
            messages.error(request, "The passwords do not match.")
            return render(request, self.template_name)
        user.set_password(password)
        user.save(update_fields=["password"])
        request.session.pop("password_reset_phone", None)
        login(request, user)
        messages.success(request, "Your password has been reset.")
        return redirect(get_post_login_redirect(user))
