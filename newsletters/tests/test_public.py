import re

from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from newsletters.models import Issue, Newsletter, Subscription

from .helpers import BaseTestCase


class DiscoveryTests(BaseTestCase):
    def test_home_and_discover_list_public_newsletters_only(self):
        Newsletter.objects.create(owner=self.other, title="Hidden Gem", description="x", is_public=False)
        Newsletter.objects.create(owner=self.other, title="Closed Shop", description="x", accepting_subscribers=False)
        for name in ("home", "discover"):
            response = self.client.get(reverse(name))
            self.assertContains(response, "The Friday Letter")
            self.assertNotContains(response, "Hidden Gem")
            self.assertNotContains(response, "Closed Shop")

    def test_search(self):
        Newsletter.objects.create(owner=self.other, title="Gardening Weekly", description="Plants")
        response = self.client.get(reverse("discover"), {"q": "plants"})
        self.assertContains(response, "Gardening Weekly")
        self.assertNotContains(response, "The Friday Letter")

    def test_unlisted_newsletter_is_reachable_by_link(self):
        self.newsletter.is_public = False
        self.newsletter.save()
        self.assertEqual(self.client.get(self.newsletter.get_absolute_url()).status_code, 200)

    def test_unknown_newsletter_404_uses_branded_page(self):
        response = self.client.get("/n/nope/")
        self.assertContains(response, "couldn't find that page", status_code=404)

    def test_legacy_subscribe_url_redirects(self):
        response = self.client.get(f"/newsletters/subscribe/{self.newsletter.pk}/")
        self.assertRedirects(response, self.newsletter.get_absolute_url(), status_code=301)


class SubscribeFlowTests(BaseTestCase):
    def subscribe(self, email="reader@example.com", **extra):
        return self.client.post(self.newsletter.get_absolute_url(), {"email": email, **extra})

    def test_double_opt_in_end_to_end(self):
        response = self.subscribe("Reader@Example.com")
        self.assertRedirects(response, reverse("subscription_pending", args=[self.newsletter.slug]))

        sub = Subscription.objects.get()
        self.assertEqual((sub.email, sub.status), ("reader@example.com", Subscription.Status.PENDING))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@example.com"])
        self.assertIn(str(sub.token), mail.outbox[0].body)

        # Pending readers must not be mailed issues.
        self.assertFalse(self.newsletter.subscriptions.confirmed().exists())

        confirmed = self.client.get(reverse("subscription_confirm", args=[sub.token]))
        self.assertContains(confirmed, "You're subscribed")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CONFIRMED)

    def test_confirmed_subscriber_resubscribing_gets_no_email_and_no_hint(self):
        self.subscriber("reader@example.com")
        response = self.subscribe("reader@example.com")
        self.assertRedirects(response, reverse("subscription_pending", args=[self.newsletter.slug]))
        self.assertEqual(len(mail.outbox), 0)  # same response either way: no account enumeration

    def test_pending_confirmation_is_not_resent_within_five_minutes(self):
        self.subscribe()
        self.subscribe()
        self.assertEqual(len(mail.outbox), 1)

    def test_unsubscribed_reader_must_confirm_again(self):
        sub = self.subscriber("reader@example.com", status=Subscription.Status.UNSUBSCRIBED)
        old_token = sub.token
        self.subscribe()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        self.assertNotEqual(sub.token, old_token)
        self.assertEqual(len(mail.outbox), 1)

    def test_invalid_email_is_rejected(self):
        response = self.subscribe("not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subscription.objects.exists())

    def test_closed_newsletter_rejects_subscribers(self):
        self.newsletter.accepting_subscribers = False
        self.newsletter.save()
        response = self.subscribe()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subscription.objects.exists())

    def test_honeypot_silently_discards_bots(self):
        response = self.subscribe(website="http://spam.example")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NEWSLETTER_SUBSCRIBE_LIMIT=2)
    def test_rate_limit(self):
        self.subscribe("a@example.com")
        self.subscribe("b@example.com")
        response = self.subscribe("c@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many attempts")
        self.assertEqual(Subscription.objects.count(), 2)

    def test_bad_confirmation_token_is_404(self):
        response = self.client.get(reverse("subscription_confirm", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(response.status_code, 404)


class UnsubscribeTests(BaseTestCase):
    def test_get_does_not_unsubscribe_but_post_does(self):
        sub = self.subscriber("reader@example.com")
        url = reverse("unsubscribe", args=[sub.token])
        self.assertContains(self.client.get(url), "Unsubscribe from")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CONFIRMED)

        self.assertContains(self.client.post(url), "You've been unsubscribed")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.UNSUBSCRIBED)

    def test_one_click_post_works_without_csrf_token(self):
        sub = self.subscriber("reader@example.com")
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("unsubscribe", args=[sub.token]), {"List-Unsubscribe": "One-Click"})
        self.assertEqual(response.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.UNSUBSCRIBED)

    def test_unsubscribing_twice_is_harmless(self):
        sub = self.subscriber("reader@example.com", status=Subscription.Status.UNSUBSCRIBED)
        self.assertEqual(self.client.post(reverse("unsubscribe", args=[sub.token])).status_code, 200)


class PublicIssueTests(BaseTestCase):
    def test_only_sent_public_issues_are_visible(self):
        sent = self.issue(status=Issue.Status.SENT, subject="Out now")
        draft = self.issue(subject="Secret draft")
        private = self.issue(status=Issue.Status.SENT, publish_to_web=False, subject="Email only")

        self.assertContains(self.client.get(sent.get_absolute_url()), "Out now")
        self.assertEqual(self.client.get(reverse("issue_public", args=[self.newsletter.slug, draft.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("issue_public", args=[self.newsletter.slug, private.pk])).status_code, 404)

        archive = self.client.get(self.newsletter.get_absolute_url())
        self.assertContains(archive, "Out now")
        self.assertNotContains(archive, "Secret draft")
        self.assertNotContains(archive, "Email only")

    def test_issue_body_is_sanitised(self):
        issue = self.issue(status=Issue.Status.SENT, body="<script>alert(1)</script>Safe text")
        response = self.client.get(issue.get_absolute_url())
        self.assertContains(response, "Safe text")
        self.assertNotContains(response, "<script>alert")

    def test_issue_url_must_match_its_newsletter(self):
        other = Newsletter.objects.create(owner=self.other, title="Other", description="x")
        issue = self.issue(status=Issue.Status.SENT)
        self.assertEqual(self.client.get(reverse("issue_public", args=[other.slug, issue.pk])).status_code, 404)
