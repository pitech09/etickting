from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify

from accounts.models import User
from ticketing.models import Event, ScannerDevice

from .models import Organisation, OrganisationMembership, OrganisationPaymentMethod


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


class OrganisationMemberForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(label="Email address")
    password = forms.CharField(
        min_length=8,
        label="Temporary password",
        help_text="Give this to the staff member securely. They can change it after signing in.",
        widget=forms.PasswordInput,
    )
    role = forms.ChoiceField(
        choices=(
            (OrganisationMembership.Role.EVENT_MANAGER, "Event manager"),
            (OrganisationMembership.Role.EVENT_STAFF, "Event staff"),
        )
    )

    def __init__(self, *args, organisation=None, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.existing_user = None
            return email
        if OrganisationMembership.objects.filter(organisation=self.organisation, user=user).exists():
            raise forms.ValidationError("This user is already a member of the organisation.")
        self.existing_user = user
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class OrganisationMemberRoleForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=(
            (OrganisationMembership.Role.EVENT_MANAGER, "Event manager"),
            (OrganisationMembership.Role.EVENT_STAFF, "Event staff"),
        )
    )

    class Meta:
        model = OrganisationMembership
        fields = ("role",)


class ScannerDeviceForm(forms.ModelForm):
    class Meta:
        model = ScannerDevice
        fields = ("device_id", "event", "user", "active")
        help_texts = {
            "device_id": "Use a clear name such as entrance-phone-1.",
        }

    def __init__(self, *args, organisation=None, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.filter(organisation=organisation).order_by("starts_at")
        self.fields["user"].queryset = User.objects.filter(
            organisation_memberships__organisation=organisation,
            organisation_memberships__role__in=(
                OrganisationMembership.Role.OWNER,
                OrganisationMembership.Role.EVENT_MANAGER,
                OrganisationMembership.Role.EVENT_STAFF,
            ),
        ).distinct().order_by("email")

    def clean_device_id(self):
        device_id = self.cleaned_data["device_id"].strip()
        if ScannerDevice.objects.filter(device_id=device_id).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This device ID is already in use.")
        return device_id

    def clean(self):
        cleaned = super().clean()
        event = cleaned.get("event")
        user = cleaned.get("user")
        if event and event.organisation_id != self.organisation.id:
            self.add_error("event", "Choose an event belonging to this organisation.")
        if user and not OrganisationMembership.objects.filter(
            organisation=self.organisation,
            user=user,
            role__in=(
                OrganisationMembership.Role.OWNER,
                OrganisationMembership.Role.EVENT_MANAGER,
                OrganisationMembership.Role.EVENT_STAFF,
            ),
        ).exists():
            self.add_error("user", "The assigned user must be an organisation member.")
        return cleaned
