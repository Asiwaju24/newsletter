from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyDataMigrationTests(TransactionTestCase):
    """The very first version of the project (migration 0001) must upgrade without losing data."""

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_legacy_rows_get_slugs_and_confirmed_subscriptions(self):
        old = self.migrate([("newsletters", "0001_initial")])
        User = old.get_model("auth", "User")
        Newsletter = old.get_model("newsletters", "Newsletter")
        Subscriber = old.get_model("newsletters", "Subscriber")

        owner = User.objects.create(username="legacy")
        first = Newsletter.objects.create(owner=owner, title="Weekly Notes!", description="a")
        second = Newsletter.objects.create(owner=owner, title="Weekly Notes!", description="b")
        reader = Subscriber.objects.create(email="Reader@Example.com")
        reader.newsletters.add(first, second)

        new = self.migrate([("newsletters", "0004_finalize")])
        Newsletter = new.get_model("newsletters", "Newsletter")
        Subscription = new.get_model("newsletters", "Subscription")

        self.assertEqual(sorted(Newsletter.objects.values_list("slug", flat=True)), ["weekly-notes", "weekly-notes-2"])
        subs = Subscription.objects.all()
        self.assertEqual(subs.count(), 2)
        self.assertEqual({s.email for s in subs}, {"reader@example.com"})
        self.assertEqual({s.status for s in subs}, {"confirmed"})
