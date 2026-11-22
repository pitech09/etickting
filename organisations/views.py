from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import OrganisationForm, OrganisationPaymentMethodForm
from .models import OrganisationMembership, OrganisationPaymentMethod


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
            return redirect("dashboard")
    else:
        form = OrganisationForm(instance=organisation)
    return render(request, "organisations/edit.html", {
        "form": form,
        "organisation": organisation,
        "payment_methods": organisation.payment_methods.all(),
        "payment_method_form": OrganisationPaymentMethodForm(),
    })


def _manageable_organisation(request, organisation_id):
    membership = get_object_or_404(
        OrganisationMembership.objects.select_related("organisation"),
        organisation_id=organisation_id,
        user=request.user,
    )
    if not membership.can_manage():
        return None
    return membership.organisation


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
            return redirect("organisations:edit", organisation_id=organisation.id)
    else:
        form = OrganisationPaymentMethodForm()
    return render(request, "organisations/edit.html", {
        "form": OrganisationForm(instance=organisation),
        "organisation": organisation,
        "payment_methods": organisation.payment_methods.all(),
        "payment_method_form": form,
    })


@login_required
def payment_method_delete(request, organisation_id, method_id):
    organisation = _manageable_organisation(request, organisation_id)
    if organisation is None:
        return redirect("dashboard")
    if request.method == "POST":
        OrganisationPaymentMethod.objects.filter(
            pk=method_id, organisation=organisation
        ).delete()
    return redirect("organisations:edit", organisation_id=organisation.id)
