from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User
from .services import normalize_phone


class RegistrationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].required = True
        self.fields["phone_number"].label = "Phone number"
        self.fields["phone_number"].widget.attrs.update({
            "autocomplete": "tel",
            "placeholder": "+266 5XXX XXXX",
        })

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_phone_number(self):
        try:
            phone = normalize_phone(self.cleaned_data.get("phone_number"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone


class OrganiserRegistrationForm(RegistrationForm):
    organisation_name = forms.CharField(max_length=180, label="Organisation name")
    organisation_description = forms.CharField(
        required=False,
        label="Organisation description",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AccountDetailsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].label = "Phone number"
        self.fields["phone_number"].widget.attrs.update({
            "autocomplete": "tel",
            "placeholder": "+266 5XXX XXXX",
        })

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone_number(self):
        phone_value = self.cleaned_data.get("phone_number")
        if not phone_value:
            return phone_value
        try:
            phone = normalize_phone(phone_value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if User.objects.filter(phone_number=phone).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone
