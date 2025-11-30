from django import forms


class PreferenceStepForm(forms.Form):
    user_input = forms.CharField(widget=forms.Textarea, label="Your response")