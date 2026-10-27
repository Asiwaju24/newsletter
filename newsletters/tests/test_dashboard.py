import csv
import io
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from newsletters.models import Issue, Newsletter, Subscription

from .helpers import BaseTestCase


class AccessControlTests(BaseTestCase):
    def test_anonymous_users_are_sent_to_login(self):
        issue = self.issue()
        for url in (
            reverse("dashboard"),
            reverse("newsletter_create"),
            reverse("newsletter_manage", args=[self.newsletter.pk]),
            reverse("issue_detail", args=[issue.pk]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response["Location"].startswith("/accounts/login/"), url)

    def test_other_users_cannot_touch_my_data(self):
        issue = self.issue()
        sub = self.subscriber("reader@example.com")
        self.login(self.other)
        pk = self.newsletter.pk
        for url in (
            reverse("newsletter_manage", args=[pk]),
            reverse("newsletter_settings", args=[pk]),
            reverse("newsletter_delete", args=[pk]),
            reverse("subscriber_list", args=[pk]),
            reverse("subscriber_export", args=[pk]),
            reverse("issue_create", args=[pk]),
            reverse("issue_detail", args=[issue.pk]),
            reverse("issue_edit", args=[issue.pk]),
            reverse("issue_delete", args=[issue.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in (
            reverse("issue_action", args=[issue.pk]),
            reverse("subscriber_remove", args=[pk, sub.pk]),
            reverse("newsletter_delete", args=[pk]),
            reverse("issue_delete", args=[issue.pk]),
        ):
            self.assertEqual(self.client.post(url, {"action": "send_now"}).status_code, 404, url)
        self.assertTrue(Subscription.objects.filter(pk=sub.pk).exists())
        self.assertTrue(Issue.objects.filter(pk=issue.pk).exists())

    def test_dashboard_only_lists_own_newsletters(self):
        Newsletter.objects.create(owner=self.other, title="Bobs Private Notes", description="x")
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "The Friday Letter")
        self.assertNotContains(response, "Bobs Private Notes")

    def test_actions_require_post(self):
        issue = self.issue()
        self.login()
        self.assertEqual(self.client.get(reverse("issue_action", args=[issue.pk])).status_code, 405)


class NewsletterManagementTests(BaseTestCase):
    def test_empty_dashboard_invites_first_newsletter(self):
        Newsletter.objects.all().delete()
        self.login()
        self.assertContains(self.client.get(reverse("dashboard")), "Start your first newsletter")

    def test_dashboard_stats(self):
        self.subscriber("a@example.com")
        self.subscriber("b@example.com")
        self.subscriber("c@example.com", status=Subscription.Status.PENDING)
        self.issue(status=Issue.Status.SENT)
        self.login()
        stats = self.client.get(reverse("dashboard")).context["stats"]
        self.assertEqual((stats["subscribers"], stats["issues_sent"], stats["newsletters"]), (2, 1, 1))

    def test_create_newsletter_assigns_owner(self):
        self.login()
        response = self.client.post(reverse("newsletter_create"), {"title": "Brand New", "description": "Hello", "is_public": "on", "accepting_subscribers": "on"})
        created = Newsletter.objects.get(title="Brand New")
        self.assertEqual(created.owner, self.owner)
        self.assertRedirects(response, reverse("issue_create", args=[created.pk]))

    def test_settings_update_and_delete(self):
        self.login()
        url = reverse("newsletter_settings", args=[self.newsletter.pk])
        self.client.post(url, {"title": "Renamed", "description": "New", "from_name": "Ada", "accepting_subscribers": "on"})
        self.newsletter.refresh_from_db()
        self.assertEqual((self.newsletter.title, self.newsletter.from_name, self.newsletter.is_public), ("Renamed", "Ada", False))
        self.client.post(reverse("newsletter_delete", args=[self.newsletter.pk]))
        self.assertFalse(Newsletter.objects.filter(pk=self.newsletter.pk).exists())

    def test_subscriber_list_filter_search_and_remove(self):
        keep = self.subscriber("keep@example.com")
        self.subscriber("wait@example.com", status=Subscription.Status.PENDING)
        self.login()
        url = reverse("subscriber_list", args=[self.newsletter.pk])
        self.assertContains(self.client.get(url, {"status": "pending"}), "wait@example.com")
        self.assertNotContains(self.client.get(url, {"status": "pending"}), "keep@example.com")
        self.assertContains(self.client.get(url, {"q": "keep"}), "keep@example.com")
        self.client.post(reverse("subscriber_remove", args=[self.newsletter.pk, keep.pk]))
        self.assertFalse(Subscription.objects.filter(pk=keep.pk).exists())

    def test_csv_export_neutralises_formula_injection(self):
        self.subscriber("=cmd@example.com")
        self.subscriber("fine@example.com")
        self.login()
        response = self.client.get(reverse("subscriber_export", args=[self.newsletter.pk]))
        self.assertEqual(response["Content-Type"], "text/csv")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][:2], ["email", "status"])
        emails = {row[0] for row in rows[1:]}
        self.assertIn("'=cmd@example.com", emails)
        self.assertIn("fine@example.com", emails)


class IssueEditingTests(BaseTestCase):
    def test_create_and_edit_issue(self):
        self.login()
        response = self.client.post(reverse("issue_create", args=[self.newsletter.pk]), {"subject": "Hello", "body": "# Hi", "publish_to_web": "on"})
        issue = Issue.objects.get()
        self.assertRedirects(response, reverse("issue_detail", args=[issue.pk]))
        self.assertEqual(issue.status, Issue.Status.DRAFT)
        self.client.post(reverse("issue_edit", args=[issue.pk]), {"subject": "Hello again", "body": "Updated"})
        issue.refresh_from_db()
        self.assertEqual(issue.subject, "Hello again")

    def test_sent_issues_cannot_be_edited(self):
        issue = self.issue(status=Issue.Status.SENT)
        self.login()
        response = self.client.post(reverse("issue_edit", args=[issue.pk]), {"subject": "Tampered", "body": "x"})
        self.assertRedirects(response, reverse("issue_detail", args=[issue.pk]))
        issue.refresh_from_db()
        self.assertEqual(issue.subject, "Issue one")

    def test_markdown_preview_endpoint(self):
        self.login()
        response = self.client.post(reverse("markdown_preview"), {"text": "**hi**<script>x</script>"})
        html = response.json()["html"]
        self.assertIn("<strong>hi</strong>", html)
        self.assertNotIn("<script", html)

    def test_preview_requires_login(self):
        self.assertEqual(self.client.post(reverse("markdown_preview"), {"text": "x"}).status_code, 302)


class SendingFromDashboardTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.confirmed = [self.subscriber("a@example.com"), self.subscriber("b@example.com")]
        self.subscriber("pending@example.com", status=Subscription.Status.PENDING)
        self.subscriber("gone@example.com", status=Subscription.Status.UNSUBSCRIBED)
        self.draft = self.issue(subject="Big news", preheader="Short preview", body="Hello **world**")
        self.login()

    def act(self, issue=None, **data):
        return self.client.post(reverse("issue_action", args=[(issue or self.draft).pk]), data)

    @override_settings(NEWSLETTER_SEND_INLINE=True)
    def test_send_now_reaches_only_confirmed_subscribers(self):
        self.act(action="send_now")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.SENT)
        self.assertEqual(self.draft.recipients_count, 2)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["a@example.com", "b@example.com"])

    @override_settings(NEWSLETTER_SEND_INLINE=True, DEFAULT_FROM_EMAIL="Dispatch <no-reply@mail.example.com>", SITE_URL="https://letters.example.com")
    def test_email_content_and_headers(self):
        self.act(action="send_now")
        message = next(m for m in mail.outbox if m.to == ["a@example.com"])
        token = str(self.confirmed[0].token)
        self.assertEqual(message.subject, "Big news")
        self.assertEqual(message.from_email, "The Friday Letter <no-reply@mail.example.com>")
        self.assertEqual(message.reply_to, ["ada@example.com"])
        unsubscribe_url = f"https://letters.example.com/subscriptions/unsubscribe/{token}/"
        self.assertEqual(message.extra_headers["List-Unsubscribe"], f"<{unsubscribe_url}>")
        self.assertEqual(message.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertIn(unsubscribe_url, message.body)
        html = message.alternatives[0][0]
        self.assertIn(unsubscribe_url, html)
        self.assertIn("<strong>world</strong>", html)
        self.assertIn("Short preview", html)

    @override_settings(NEWSLETTER_SEND_INLINE=False)
    def test_queued_mode_waits_for_the_worker_command(self):
        self.act(action="send_now")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.SCHEDULED)
        self.assertEqual(len(mail.outbox), 0)
        call_command("send_queued_issues", stdout=io.StringIO())
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.SENT)
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(NEWSLETTER_SEND_INLINE=False)
    def test_scheduled_issue_waits_until_due(self):
        when = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.act(action="schedule", scheduled_at=when)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.SCHEDULED)
        call_command("send_queued_issues", stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 0)  # not due yet

        Issue.objects.filter(pk=self.draft.pk).update(scheduled_at=timezone.now() - timedelta(minutes=1))
        call_command("send_queued_issues", stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 2)

    def test_cannot_schedule_in_the_past(self):
        when = timezone.localtime(timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        self.act(action="schedule", scheduled_at=when)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.DRAFT)

    def test_schedule_can_be_cancelled(self):
        when = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.act(action="schedule", scheduled_at=when)
        self.act(action="unschedule")
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.status, self.draft.scheduled_at), (Issue.Status.DRAFT, None))

    def test_cannot_send_without_confirmed_subscribers(self):
        Subscription.objects.confirmed().update(status=Subscription.Status.UNSUBSCRIBED)
        self.act(action="send_now")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.DRAFT)

    @override_settings(NEWSLETTER_SEND_INLINE=True)
    def test_an_issue_cannot_be_sent_twice(self):
        self.act(action="send_now")
        self.act(action="send_now")
        self.assertEqual(len(mail.outbox), 2)

    def test_test_email_goes_to_one_address_and_records_nothing(self):
        self.act(action="test", email="me@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["me@example.com"])
        self.assertTrue(mail.outbox[0].subject.startswith("[Test] "))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, Issue.Status.DRAFT)
        self.assertFalse(self.draft.deliveries.exists())

    def test_failed_test_email_is_reported_not_raised(self):
        with mock.patch("newsletters.services.send_test", side_effect=OSError("smtp down")):
            response = self.client.post(
                reverse("issue_action", args=[self.draft.pk]), {"action": "test", "email": "me@example.com"}, follow=True
            )
        self.assertContains(response, "test email couldn")
