from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label="Your name", max_length=150)
    email = forms.EmailField(label="Email address")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "email", "username")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in.")
        return email
