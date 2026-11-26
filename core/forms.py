from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, label="Your name")
    email = forms.EmailField(label="Your email")
    subject = forms.CharField(max_length=160)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 7}))
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to submit this form.")
        return value
