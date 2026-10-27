from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import SignupForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("newsletter_create")
    return render(request, "accounts/form_page.html", {
        "form": form, "title": "Create your account", "submit": "Create my account",
        "footer": 'Already have an account? <a href="/accounts/login/">Log in</a>',
    })
