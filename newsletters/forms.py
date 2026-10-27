from django import forms
from django.utils import timezone

from .models import Issue, Newsletter


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = Newsletter
        fields = ["title", "description", "from_name", "reply_to", "is_public", "accepting_subscribers"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
        labels = {
            "title": "Newsletter name",
            "description": "What is it about?",
            "from_name": "Name your emails come from",
            "reply_to": "Where should replies go?",
            "is_public": "Show it in the public directory",
            "accepting_subscribers": "Let new people join",
        }
        help_texts = {
            "description": "A sentence or two. People read this before they decide to join.",
            "from_name": "This is the sender name people see in their inbox. Leave blank to use the newsletter name.",
            "reply_to": "When someone replies to your email, it lands here. Leave blank to use your account email.",
            "is_public": "If you turn this off, only people with your link can find it.",
            "accepting_subscribers": "Turn this off to close sign-ups. People already subscribed keep getting emails.",
        }

    def clean_title(self):
        return self.cleaned_data["title"].strip()


class SubscribeForm(forms.Form):
    email = forms.EmailField(
        max_length=254, label="Email address",
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}),
    )
    # Honeypot: real visitors never see or fill this in; bots usually do.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = ["subject", "preheader", "body", "publish_to_web"]
        labels = {"subject": "Subject", "preheader": "Preview text", "publish_to_web": "Also show this email on my public page after it's sent"}
        help_texts = {
            "preheader": "The short line people see next to the subject in their inbox. Optional.",
            "publish_to_web": "",
        }
        widgets = {
            "body": forms.Textarea(attrs={"rows": 18, "spellcheck": "true", "data-editor": ""}),
        }


class ScheduleForm(forms.Form):
    scheduled_at = forms.DateTimeField(
        label="Send at",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
    )

    def clean_scheduled_at(self):
        when = self.cleaned_data["scheduled_at"]
        if when <= timezone.now():
            raise forms.ValidationError("Pick a time in the future, or use “Send now”.")
        return when


class TestSendForm(forms.Form):
    email = forms.EmailField(label="Send test to")
