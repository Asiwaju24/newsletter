from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views


urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(
        template_name="accounts/form_page.html", redirect_authenticated_user=True,
        extra_context={"title": "Log in", "submit": "Log in", "footer": (
            '<a href="/accounts/password-reset/">Forgot your password?</a> · '
            'New here? <a href="/accounts/signup/">Create an account</a>'
        )}), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-change/", auth_views.PasswordChangeView.as_view(
        template_name="accounts/form_page.html", success_url=reverse_lazy("password_change_done"),
        extra_context={"title": "Change password", "submit": "Update password"}), name="password_change"),
    path("password-change/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="accounts/message.html",
        extra_context={"title": "Password updated", "message": "Your password has been changed."}), name="password_change_done"),
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/form_page.html",
        email_template_name="accounts/email/password_reset.txt",
        subject_template_name="accounts/email/password_reset_subject.txt",
        success_url=reverse_lazy("password_reset_done"),
        extra_email_context={"site_name": settings.SITE_NAME},
        extra_context={"title": "Reset your password", "submit": "Send reset link",
                       "intro": "Type the email you signed up with. We'll send you a link to choose a new password."}), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/message.html",
        extra_context={"title": "Check your inbox", "message": "If there's an account with that email, we've sent it a link to reset your password."}), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/form_page.html", success_url=reverse_lazy("password_reset_complete"),
        extra_context={"title": "Choose a new password", "submit": "Save password"}), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/message.html",
        extra_context={"title": "Password changed", "message": "You can now log in with your new password.",
                       "link_url": "/accounts/login/", "link_label": "Log in"}), name="password_reset_complete"),
]
