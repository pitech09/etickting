from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User
from organisations.forms import OrganisationForm


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class OrganiserRegistrationForm(RegistrationForm):
    organisation_name = forms.CharField(max_length=180, label="Organisation name")
    organisation_description = forms.CharField(
        required=False,
        label="Organisation description",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
