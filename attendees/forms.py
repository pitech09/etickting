from django import forms

from .models import AttendeeProfile


class AttendeeProfileForm(forms.ModelForm):
    class Meta:
        model = AttendeeProfile
        fields = ("display_name", "phone_number", "photo")
        widgets = {"photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"})}

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Photo must be 5 MB or smaller.")
        return photo
