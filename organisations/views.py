from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    OrganisationForm,
    OrganisationMemberForm,
    OrganisationMemberRoleForm,
    OrganisationPaymentMethodForm,
    ScannerDeviceForm,
)
from .models import OrganisationMembership, OrganisationPaymentMethod
from ticketing.models import ScannerDevice


@login_required
def organisation_create(request):
    if request.method == "POST":
        form = OrganisationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                organisation = form.save()
                OrganisationMembership.objects.create(
                    organisation=organisation,
                    user=request.user,
                    role=OrganisationMembership.Role.OWNER,
                )
            return redirect("dashboard")
    else:
        form = OrganisationForm()
    return render(request, "organisations/create.html", {"form": form})


@login_required
def organisation_update(request, organisation_id):
    membership = get_object_or_404(
        OrganisationMembership.objects.select_related("organisation"),
        organisation_id=organisation_id,
        user=request.user,
    )
    if not membership.can_manage():
        return redirect("dashboard")
    organisation = membership.organisation
    if request.method == "POST":
        form = OrganisationForm(request.POST, instance=organisation)
        if form.is_valid():
            form.save()
            return _organisation_settings(request, organisation, "general")
    else:
        form = OrganisationForm(instance=organisation)
    return render(request, "organisations/edit.html", _settings_context(
        organisation,
        form=form,
        payment_method_form=OrganisationPaymentMethodForm(),
        active_tab=request.GET.get("tab", "general"),
        is_owner=membership.role == OrganisationMembership.Role.OWNER,
    ))


def _settings_context(
    organisation,
    form=None,
    payment_method_form=None,
    member_form=None,
    device_form=None,
    active_tab="general",
    is_owner=None,
):
    allowed_tabs = {"general", "payments", "team", "devices"}
    if active_tab not in allowed_tabs:
        active_tab = "general"
    if is_owner is None:
        is_owner = False
    return {
        "form": form or OrganisationForm(instance=organisation),
        "organisation": organisation,
        "payment_methods": organisation.payment_methods.all(),
        "payment_method_form": payment_method_form or OrganisationPaymentMethodForm(),
        "memberships": organisation.memberships.select_related("user"),
        "devices": ScannerDevice.objects.filter(event__organisation=organisation).select_related("event", "user"),
        "member_form": member_form or OrganisationMemberForm(organisation=organisation),
        "device_form": device_form or ScannerDeviceForm(organisation=organisation),
        "active_tab": active_tab,
        "is_owner": is_owner,
    }


def _manageable_organisation(request, organisation_id):
    membership = get_object_or_404(
        OrganisationMembership.objects.select_related("organisation"),
        organisation_id=organisation_id,
        user=request.user,
    )
    if not membership.can_manage():
        return None
    return membership.organisation


def _owner_organisation(request, organisation_id):
    membership = get_object_or_404(
        OrganisationMembership.objects.select_related("organisation"),
        organisation_id=organisation_id,
        user=request.user,
        role=OrganisationMembership.Role.OWNER,
    )
    return membership.organisation


def _organisation_settings(request, organisation, tab="general"):
    url = reverse("organisations:edit", kwargs={"organisation_id": organisation.id})
    return redirect(f"{url}?tab={tab}")


@login_required
def member_add(request, organisation_id):
    organisation = _owner_organisation(request, organisation_id)
    form = OrganisationMemberForm(request.POST or None, organisation=organisation)
    if request.method == "POST" and form.is_valid():
        user = getattr(form, "existing_user", None)
        if user is None:
            from accounts.models import User

            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
        OrganisationMembership.objects.create(
            organisation=organisation,
            user=user,
            role=form.cleaned_data["role"],
        )
        return _organisation_settings(request, organisation, "team")
    if form.errors:
        messages.error(request, "Member could not be added. Check that the account exists and is not already a member.")
    return _organisation_settings(request, organisation, "team")


@login_required
def member_update(request, organisation_id, membership_id):
    organisation = _owner_organisation(request, organisation_id)
    membership = get_object_or_404(
        OrganisationMembership, pk=membership_id, organisation=organisation
    )
    if membership.role != OrganisationMembership.Role.OWNER and request.method == "POST":
        form = OrganisationMemberRoleForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
    return _organisation_settings(request, organisation, "team")


@login_required
def member_remove(request, organisation_id, membership_id):
    organisation = _owner_organisation(request, organisation_id)
    membership = get_object_or_404(
        OrganisationMembership, pk=membership_id, organisation=organisation
    )
    if request.method == "POST" and membership.role != OrganisationMembership.Role.OWNER:
        membership.delete()
    return _organisation_settings(request, organisation, "team")


@login_required
def device_create(request, organisation_id):
    organisation = _owner_organisation(request, organisation_id)
    form = ScannerDeviceForm(request.POST or None, organisation=organisation)
    if request.method == "POST" and form.is_valid():
        form.save()
        return _organisation_settings(request, organisation, "devices")
    if form.errors:
        messages.error(request, "Scanner device could not be added. Check the form details.")
    return _organisation_settings(request, organisation, "devices")


@login_required
def device_deactivate(request, organisation_id, device_id):
    organisation = _owner_organisation(request, organisation_id)
    device = get_object_or_404(ScannerDevice, pk=device_id, event__organisation=organisation)
    if request.method == "POST":
        device.active = False
        device.save(update_fields=["active"])
    return _organisation_settings(request, organisation, "devices")


@login_required
def payment_method_create(request, organisation_id):
    organisation = _manageable_organisation(request, organisation_id)
    if organisation is None:
        return redirect("dashboard")
    if request.method == "POST":
        form = OrganisationPaymentMethodForm(request.POST)
        if form.is_valid():
            method = form.save(commit=False)
            method.organisation = organisation
            method.save()
            return _organisation_settings(request, organisation, "payments")
    else:
        form = OrganisationPaymentMethodForm()
    return render(request, "organisations/edit.html", _settings_context(
        organisation,
        payment_method_form=form,
        active_tab="payments",
        is_owner=OrganisationMembership.objects.filter(
            organisation=organisation,
            user=request.user,
            role=OrganisationMembership.Role.OWNER,
        ).exists(),
    ))


@login_required
def payment_method_delete(request, organisation_id, method_id):
    organisation = _manageable_organisation(request, organisation_id)
    if organisation is None:
        return redirect("dashboard")
    if request.method == "POST":
        OrganisationPaymentMethod.objects.filter(
            pk=method_id, organisation=organisation
        ).delete()
    return _organisation_settings(request, organisation, "payments")
