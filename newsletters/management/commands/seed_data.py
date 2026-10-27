"""Fill the database with realistic demo data for manual testing.

    python manage.py seed_data            # create demo data (skips if already seeded)
    python manage.py seed_data --reset    # wipe the demo accounts' data and recreate it
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from newsletters.models import Delivery, Issue, Newsletter, Subscription

User = get_user_model()

DEMO_USERS = [
    # username, email, first name
    ("demo", "demo@example.com", "Demo"),
    ("other", "other@example.com", "Other"),  # a second creator, to check data isolation
]

NEWSLETTERS = [
    # owner, title, description, extra fields
    ("demo", "The Friday Letter",
     "Four things worth your Friday: one essay, two links, and a question for you to answer. Written for people who read slowly.", {}),
    ("demo", "Field Notes from Lagos",
     "Short dispatches on building software and small businesses in West Africa.", {"from_name": "Ada from Field Notes"}),
    ("demo", "Private Beta Notes",
     "An unlisted newsletter: reachable by link, but not shown in Discover.", {"is_public": False}),
    ("demo", "Closed Cohort",
     "A newsletter that has stopped accepting new subscribers.", {"accepting_subscribers": False}),
    ("other", "Gardening Weekly",
     "Seasonal tips for small gardens. Belongs to the second demo user.", {}),
]

SENT_ISSUES = [
    ("Why slow reading wins", "A short case for taking your time.",
     "## Start here\n\nMost of what we read is skimmed. **This issue is for the rest.**\n\n"
     "> The best sentences reward a second look.\n\n- One essay\n- Two links\n- One question\n\n"
     "Reply and tell me what you think.\n\n[Read the source](https://example.com)"),
    ("Notes on notebooks", "What I learned from filling forty of them.",
     "## The short version\n\nWrite less, **date everything**, and keep one notebook per project.\n\n"
     "| Notebook | Verdict |\n|---|---|\n| Dotted | Keeper |\n| Lined | Fine |\n\nMore next week."),
    ("The reader mailbag", "Your questions, answered.",
     "### Three questions this week\n\n1. How do you choose what to read?\n2. Paper or screen?\n3. Is a morning routine worth it?\n\n"
     "Answers below, in order.\n\n```\nread first, decide later\n```"),
]


class Command(BaseCommand):
    help = "Create demo users, newsletters, subscribers and issues for manual testing."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo users' newsletters first.")
        parser.add_argument("--subscribers", type=int, default=40, help="Subscribers per newsletter (default 40).")
        parser.add_argument("--password", default="demo-pass-1234", help="Password for the demo users.")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is off.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed data while DEBUG is off. Pass --force if you really mean it.")

        rng = random.Random(42)  # same data every run
        with transaction.atomic():
            users = self._users(options["password"])
            if options["reset"]:
                deleted, _ = Newsletter.objects.filter(owner__in=users.values()).delete()
                self.stdout.write(f"Reset: removed {deleted} rows.")
            elif Newsletter.objects.filter(owner__in=users.values()).exists():
                self.stdout.write(self.style.WARNING("Demo data already exists. Use --reset to recreate it."))
                return

            for owner, title, description, extra in NEWSLETTERS:
                newsletter = Newsletter.objects.create(owner=users[owner], title=title, description=description, **extra)
                subs = self._subscribers(newsletter, options["subscribers"], rng)
                self._issues(newsletter, subs, rng)

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write(
            f"  Log in as  demo / {options['password']}   (other creator: other / {options['password']})\n"
            f"  Then try:  /dashboard/   /discover/   /n/the-friday-letter/"
        )

    def _users(self, password):
        users = {}
        for username, email, first_name in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email, "first_name": first_name})
            user.set_password(password)
            user.save()
            users[username] = user
        return users

    def _subscribers(self, newsletter, count, rng):
        """~70% confirmed, ~15% pending, ~15% unsubscribed, spread over the last 90 days."""
        now = timezone.now()
        subs = []
        for i in range(count):
            roll = rng.random()
            status = (Subscription.Status.CONFIRMED if roll < 0.70
                      else Subscription.Status.PENDING if roll < 0.85
                      else Subscription.Status.UNSUBSCRIBED)
            created = now - timedelta(days=rng.randint(0, 90), hours=rng.randint(0, 23))
            sub = Subscription(newsletter=newsletter, email=f"reader{i + 1}.{newsletter.slug[:12]}@example.com",
                               status=status, created_at=created)
            if status != Subscription.Status.PENDING:
                sub.confirmed_at = created + timedelta(minutes=rng.randint(1, 600))
            if status == Subscription.Status.UNSUBSCRIBED:
                sub.unsubscribed_at = sub.confirmed_at + timedelta(days=rng.randint(1, 30))
            sub.save()
            subs.append(sub)
        return subs

    def _issues(self, newsletter, subs, rng):
        now = timezone.now()
        confirmed = [s for s in subs if s.status == Subscription.Status.CONFIRMED]
        unsubscribed = [s for s in subs if s.status == Subscription.Status.UNSUBSCRIBED]

        # Sent issues, oldest first, with a delivery record per recipient.
        for n, (subject, preheader, body) in enumerate(SENT_ISSUES):
            sent_at = now - timedelta(days=7 * (len(SENT_ISSUES) - n), hours=2)
            issue = Issue.objects.create(
                newsletter=newsletter, subject=subject, preheader=preheader, body=body,
                status=Issue.Status.SENT, sent_at=sent_at, scheduled_at=sent_at,
                publish_to_web=(n != 1),  # one email-only issue, to test the archive filter
            )
            Issue.objects.filter(pk=issue.pk).update(created_at=sent_at - timedelta(days=1))
            deliveries = [Delivery(issue=issue, subscription=s, status=Delivery.Status.SENT, sent_at=sent_at) for s in confirmed]
            deliveries += [Delivery(issue=issue, subscription=s, status=Delivery.Status.SKIPPED) for s in unsubscribed[:1]]
            if n == len(SENT_ISSUES) - 1 and len(deliveries) > 3:
                # The latest issue has two failures so "Retry failed" can be tried.
                for d in deliveries[:2]:
                    d.status, d.sent_at, d.error = Delivery.Status.FAILED, None, "550 mailbox unavailable (seeded)"
            Delivery.objects.bulk_create(deliveries)
            sent = sum(d.status == Delivery.Status.SENT for d in deliveries)
            Issue.objects.filter(pk=issue.pk).update(recipients_count=sent)

        # One of each remaining state.
        Issue.objects.create(newsletter=newsletter, subject="Draft: what I'm reading this month",
                             body="## Work in progress\n\nA few notes still to fill in.", status=Issue.Status.DRAFT)
        Issue.objects.create(newsletter=newsletter, subject="Coming up: the year in review", preheader="Scheduled for later this week.",
                             body="Scheduled issue body.", status=Issue.Status.SCHEDULED, scheduled_at=now + timedelta(days=3))
        if newsletter.slug == "the-friday-letter":
            # Already due: sending it is how you test the worker.
            Issue.objects.create(newsletter=newsletter, subject="Due now: test the queue worker",
                                 body="Run `python manage.py send_queued_issues` and watch this go out.",
                                 status=Issue.Status.SCHEDULED, scheduled_at=now - timedelta(minutes=5))
