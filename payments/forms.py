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
        self.fields["proof_image"].required = False

    class Meta:
        model = Payment
        fields = ("payment_method", "provider_reference", "sender_phone", "proof_image")
        labels = {
            "provider": "Payment method",
            "provider_reference": "Transaction/reference number",
            "proof_image": "Payment screenshot",
            "sender_phone": "Sender mobile number",
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

    def clean_sender_phone(self):
        return self.cleaned_data["sender_phone"].strip()

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        reference = cleaned.get("provider_reference", "")
        if method and reference:
            duplicate = Payment.objects.filter(
                provider=method.provider,
                provider_reference__iexact=reference,
            ).exclude(pk=self.instance.pk).exists()
            if duplicate:
                self.add_error("provider_reference", "This transaction reference has already been submitted.")
        return cleaned


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
    received_amount_maloti = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label="Verified amount received (Maloti)",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") == "approve" and cleaned.get("received_amount_maloti") is None:
            self.add_error("received_amount_maloti", "Enter the amount confirmed in the mobile money record.")
        return cleaned
