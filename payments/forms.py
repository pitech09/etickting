from django import forms

from organisations.models import OrganisationPaymentMethod

from .models import Payment


class ManualPaymentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        organisation = kwargs.pop("organisation", None)
        super().__init__(*args, **kwargs)
        methods = OrganisationPaymentMethod.objects.filter(
            organisation=organisation, is_active=True
        ) if organisation else OrganisationPaymentMethod.objects.none()
        self.fields["payment_method"].queryset = methods
        self.fields["payment_method"].label = "Pay using"
        self.fields["payment_method"].empty_label = "Choose a payment destination"
        self.fields["payment_method"].label_from_instance = lambda method: (
            f"{method.get_provider_display()} · {method.label} · {method.account_number}"
        )
        self.fields["proof_image"].required = True

    class Meta:
        model = Payment
        fields = ("payment_method", "provider_reference", "proof_image")
        labels = {
            "provider": "Payment method",
            "provider_reference": "Transaction/reference number",
            "proof_image": "Payment screenshot",
        }
        widgets = {
            "proof_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}),
        }

    def clean_proof_image(self):
        image = self.cleaned_data.get("proof_image")
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Screenshot must be 5 MB or smaller.")
        return image

    def clean_provider_reference(self):
        reference = self.cleaned_data["provider_reference"].strip()
        if not reference:
            raise forms.ValidationError("Enter the transaction or payment reference.")
        return reference


class PaymentReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(("approve", "Approve payment"), ("reject", "Reject payment")),
        widget=forms.HiddenInput,
    )
    review_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Review note",
    )
