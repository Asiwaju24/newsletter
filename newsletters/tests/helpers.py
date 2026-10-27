from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from newsletters.models import Issue, Newsletter, Subscription

User = get_user_model()


class BaseTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("ada", "ada@example.com", "s3cret-passphrase", first_name="Ada")
        self.other = User.objects.create_user("bob", "bob@example.com", "s3cret-passphrase")
        self.newsletter = Newsletter.objects.create(owner=self.owner, title="The Friday Letter", description="Weekly notes.")

    def login(self, user=None):
        self.client.force_login(user or self.owner)

    def subscriber(self, email, status=Subscription.Status.CONFIRMED, newsletter=None):
        sub = Subscription.objects.create(newsletter=newsletter or self.newsletter, email=email)
        if status == Subscription.Status.CONFIRMED:
            sub.confirm()
        elif status == Subscription.Status.UNSUBSCRIBED:
            sub.unsubscribe()
        sub.refresh_from_db()
        return sub

    def issue(self, **kwargs):
        defaults = {"newsletter": self.newsletter, "subject": "Issue one", "body": "Hello **world**"}
        defaults.update(kwargs)
        return Issue.objects.create(**defaults)
