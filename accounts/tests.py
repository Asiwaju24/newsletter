from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
GOOD = {"first_name": "Ada", "email": "ada@example.com", "username": "ada", "password1": "a-long-unusual-passphrase", "password2": "a-long-unusual-passphrase"}


class SignupTests(TestCase):
    def test_signup_logs_in_and_starts_onboarding(self):
        response = self.client.post(reverse("signup"), GOOD)
        self.assertRedirects(response, reverse("newsletter_create"))
        self.assertEqual(User.objects.get().email, "ada@example.com")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_email_must_be_unique_ignoring_case(self):
        User.objects.create_user("first", "ADA@example.com", "x" * 12)
        response = self.client.post(reverse("signup"), GOOD)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_weak_passwords_are_rejected(self):
        response = self.client.post(reverse("signup"), {**GOOD, "password1": "12345678", "password2": "12345678"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_logged_in_users_skip_signup(self):
        self.client.post(reverse("signup"), GOOD)
        self.assertRedirects(self.client.get(reverse("signup")), reverse("dashboard"))


class LoginLogoutTests(TestCase):
    def setUp(self):
        User.objects.create_user("ada", "ada@example.com", "a-long-unusual-passphrase")

    def test_login_honours_next(self):
        response = self.client.post(reverse("login") + "?next=/dashboard/newsletters/new/", {"username": "ada", "password": "a-long-unusual-passphrase", "next": "/dashboard/newsletters/new/"})
        self.assertRedirects(response, "/dashboard/newsletters/new/")

    def test_wrong_password(self):
        response = self.client.post(reverse("login"), {"username": "ada", "password": "nope"})
        self.assertContains(response, "Please enter a correct")

    def test_logout_requires_post(self):
        self.client.login(username="ada", password="a-long-unusual-passphrase")
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_password_reset_email_uses_site_name(self):
        self.client.post(reverse("password_reset"), {"email": "ada@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Dispatch", mail.outbox[0].subject)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_password_reset_does_not_reveal_unknown_emails(self):
        response = self.client.post(reverse("password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
