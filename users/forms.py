from django import forms
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from allauth.socialaccount.forms import SignupForm

UserModel = get_user_model()

class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            user = authenticate(request=self.request, username=email, password=password)

            if not user:
                raise forms.ValidationError("Invalid login credentials")

            cleaned_data['user'] = user
        return cleaned_data


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = UserModel
        fields = ['email']

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        pw = cleaned_data.get('password')
        pw_confirm = cleaned_data.get('password_confirm')

        if pw != pw_confirm:
            raise forms.ValidationError("Passwords do not match")
        
        validate_password(pw)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class CustomSocialSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field if it exists
        if 'username' in self.fields:
            del self.fields['username']
    
    def save(self, request):
        user = super().save(request)
        return user