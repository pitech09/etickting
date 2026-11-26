from django import forms

from .models import PlatformCommissionConfig


class PlatformCommissionForm(forms.ModelForm):
    class Meta:
        model = PlatformCommissionConfig
        fields = ("commission_rate",)
        labels = {"commission_rate": "Default commission percentage"}
        widgets = {"commission_rate": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.01"})}
