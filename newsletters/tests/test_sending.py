from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from newsletters import services
from newsletters.models import Delivery, Issue, Newsletter, Subscription

from .helpers import BaseTestCase


class SendIssueTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.subscriber("a@example.com")
        self.b = self.subscriber("b@example.com")
        self.c = self.subscriber("c@example.com")
        self.draft = self.issue()
        services.schedule_issue(self.draft)

    def test_records_a_delivery_per_recipient(self):
        result = services.send_issue(self.draft)
        self.assertEqual((result.sent, result.failed, result.skipped), (3, 0, 0))
        self.assertEqual(self.draft.deliveries.filter(status=Delivery.Status.SENT).count(), 3)
        self.draft.refresh_from_db()
        self.assertIsNotNone(self.draft.sent_at)

    def test_second_call_is_a_no_op(self):
        services.send_issue(self.draft)
        self.assertIsNone(services.send_issue(self.draft))
        self.assertEqual(len(mail.outbox), 3)

    def test_one_failure_does_not_stop_the_batch_and_can_be_retried(self):
        real_send = EmailMultiAlternatives.send

        def flaky(message, *args, **kwargs):
            if message.to == ["b@example.com"] and flaky.fail:
                raise OSError("mailbox unavailable")
            return real_send(message, *args, **kwargs)

        flaky.fail = True
        with mock.patch.object(EmailMultiAlternatives, "send", flaky):
            result = services.send_issue(self.draft)
            self.assertEqual((result.sent, result.failed), (2, 1))
            failed = self.draft.deliveries.get(status=Delivery.Status.FAILED)
            self.assertEqual(failed.subscription, self.b)
            self.assertIn("mailbox unavailable", failed.error)

            self.assertTrue(services.retry_failed(self.draft))
            flaky.fail = False
            result = services.send_issue(self.draft)
        self.assertEqual((result.sent, result.failed), (3, 0))
        # Only the failed recipient was re-attempted: nobody got a duplicate.
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["a@example.com", "b@example.com", "c@example.com"])

    def test_retry_is_refused_when_nothing_failed(self):
        services.send_issue(self.draft)
        self.assertFalse(services.retry_failed(self.draft))

    def test_readers_who_unsubscribe_mid_send_are_skipped(self):
        Delivery.objects.create(issue=self.draft, subscription=self.c)
        self.c.unsubscribe()
        result = services.send_issue(self.draft)
        self.assertEqual((result.sent, result.skipped), (2, 1))
        self.assertNotIn("c@example.com", [m.to[0] for m in mail.outbox])

    def test_stalled_sends_are_picked_up_but_fresh_ones_are_not(self):
        Issue.objects.filter(pk=self.draft.pk).update(status=Issue.Status.SENDING, sending_started_at=timezone.now())
        self.assertNotIn(self.draft, services.due_issues())
        Issue.objects.filter(pk=self.draft.pk).update(sending_started_at=timezone.now() - timedelta(hours=1))
        self.assertIn(self.draft, services.due_issues())
        self.assertIsNotNone(services.send_issue(self.draft))


class SeedDataTests(BaseTestCase):
    def run_seed(self, *args):
        import io

        from django.core.management import call_command

        call_command("seed_data", *args, stdout=io.StringIO())

    def test_seeds_every_state_and_refuses_to_duplicate(self):
        from django.test import override_settings

        with override_settings(DEBUG=True):
            self.run_seed("--subscribers", "20")
            total = Newsletter.objects.count()
            self.run_seed("--subscribers", "20")  # no --reset: a no-op
            self.assertEqual(Newsletter.objects.count(), total)
            self.assertEqual(
                {s for s in Issue.objects.values_list("status", flat=True)},
                {"draft", "scheduled", "sent"},
            )
            self.assertEqual(
                {s for s in Subscription.objects.values_list("status", flat=True)},
                {"pending", "confirmed", "unsubscribed"},
            )
            self.run_seed("--reset", "--subscribers", "20")
            self.assertEqual(Newsletter.objects.filter(owner__username="demo").count(), 4)

    def test_refuses_when_debug_is_off(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_seed()
