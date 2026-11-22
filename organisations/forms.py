from django import forms
from django.utils.text import slugify

from .models import Organisation, OrganisationPaymentMethod


class OrganisationForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = ("name", "description", "payment_number")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Organisation name is required.")
        return name

    def save(self, commit=True):
        organisation = super().save(commit=False)
        base_slug = slugify(organisation.name) or "organisation"
        slug = base_slug
        suffix = 2
        while Organisation.objects.filter(slug=slug).exclude(pk=organisation.pk).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        organisation.slug = slug
        if commit:
            organisation.save()
        return organisation


class OrganisationPaymentMethodForm(forms.ModelForm):
    class Meta:
        model = OrganisationPaymentMethod
        fields = ("provider", "label", "account_number", "instructions", "is_active", "sort_order")
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3})}

    def clean_label(self):
        return self.cleaned_data["label"].strip()

    def clean_account_number(self):
        return self.cleaned_data["account_number"].strip()
