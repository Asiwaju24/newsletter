from django.db import IntegrityError, transaction

from newsletters.models import Newsletter, Subscription
from newsletters.rendering import render_markdown

from .helpers import BaseTestCase


class NewsletterModelTests(BaseTestCase):
    def test_slug_is_generated_and_unique(self):
        second = Newsletter.objects.create(owner=self.owner, title="The Friday Letter", description="Again")
        self.assertEqual(self.newsletter.slug, "the-friday-letter")
        self.assertEqual(second.slug, "the-friday-letter-2")

    def test_slug_is_stable_after_title_change(self):
        self.newsletter.title = "Renamed"
        self.newsletter.save()
        self.assertEqual(Newsletter.objects.get(pk=self.newsletter.pk).slug, "the-friday-letter")

    def test_sender_defaults(self):
        self.assertEqual(self.newsletter.sender_name, "The Friday Letter")
        self.assertEqual(self.newsletter.reply_to_address, "ada@example.com")
        self.newsletter.from_name, self.newsletter.reply_to = "Ada", "hello@example.com"
        self.assertEqual((self.newsletter.sender_name, self.newsletter.reply_to_address), ("Ada", "hello@example.com"))


class SubscriptionModelTests(BaseTestCase):
    def test_email_is_normalised(self):
        sub = Subscription.objects.create(newsletter=self.newsletter, email="  Reader@Example.COM ")
        self.assertEqual(sub.email, "reader@example.com")

    def test_one_subscription_per_email_per_newsletter(self):
        self.subscriber("a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscription.objects.create(newsletter=self.newsletter, email="a@example.com")

    def test_same_email_can_join_different_newsletters(self):
        other = Newsletter.objects.create(owner=self.other, title="Other", description="x")
        self.subscriber("a@example.com")
        self.subscriber("a@example.com", newsletter=other)
        self.assertEqual(Subscription.objects.filter(email="a@example.com").count(), 2)

    def test_lifecycle(self):
        sub = Subscription.objects.create(newsletter=self.newsletter, email="a@example.com")
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        sub.confirm()
        self.assertIsNotNone(sub.confirmed_at)
        sub.unsubscribe()
        self.assertEqual(sub.status, Subscription.Status.UNSUBSCRIBED)
        old_token = sub.token
        sub.reset_to_pending()
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        self.assertNotEqual(sub.token, old_token)


class MarkdownTests(BaseTestCase):
    def test_renders_basic_markdown(self):
        html = render_markdown("## Title\n\n**bold** and [a link](https://example.com)")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn('href="https://example.com"', html)

    def test_strips_scripts_and_event_handlers(self):
        html = render_markdown('<script>alert(1)</script><img src="x" onerror="alert(2)"> text')
        self.assertNotIn("<script", html)
        self.assertNotIn("onerror", html)

    def test_blocks_javascript_urls(self):
        html = render_markdown("[click](javascript:alert(1))")
        self.assertNotIn("javascript:", html)
