from django.contrib.auth import views as auth_views
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from organisations.forms import OrganisationForm
from organisations.models import OrganisationMembership

from .forms import OrganiserRegistrationForm, RegistrationForm


class RegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request):
        return render(request, self.template_name, {"form": RegistrationForm()})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")
        return render(request, self.template_name, {"form": form})


class OrganiserRegisterView(View):
    template_name = "accounts/register_organiser.html"

    def get(self, request):
        return render(request, self.template_name, {"form": OrganiserRegistrationForm()})

    def post(self, request):
        form = OrganiserRegistrationForm(request.POST)
        if form.is_valid():
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
            return redirect("login")
        return render(request, self.template_name, {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        if self.get_redirect_url():
            return super().get_success_url()
        if self.request.user.is_staff or self.request.user.is_superuser:
            return reverse("admin:index")
        if self.request.user.organisation_memberships.exists():
            return reverse("dashboard")
        return reverse("customer-dashboard")


class LogoutView(auth_views.LogoutView):
    next_page = "login"
