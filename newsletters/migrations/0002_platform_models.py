import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("newsletters", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(name="newsletter", options={"ordering": ["title"]}),
        migrations.AlterField(model_name="newsletter", name="description", field=models.TextField(max_length=1000)),
        # slug starts nullable so existing rows can be back-filled in 0003.
        migrations.AddField(
            model_name="newsletter", name="slug",
            field=models.SlugField(blank=True, editable=False, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="newsletter", name="from_name",
            field=models.CharField(blank=True, help_text="Shown as the sender in your readers' inboxes. Defaults to the newsletter title.", max_length=80, verbose_name="sender name"),
        ),
        migrations.AddField(
            model_name="newsletter", name="reply_to",
            field=models.EmailField(blank=True, help_text="Replies from readers go here. Defaults to your account email.", max_length=254, verbose_name="reply-to address"),
        ),
        migrations.AddField(
            model_name="newsletter", name="is_public",
            field=models.BooleanField(default=True, help_text="Unlisted newsletters can still be joined through their link.", verbose_name="list in Discover"),
        ),
        migrations.AddField(
            model_name="newsletter", name="accepting_subscribers",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="newsletter", name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now, editable=False),
        ),
        migrations.AddField(
            model_name="newsletter", name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("status", models.CharField(choices=[("pending", "Pending confirmation"), ("confirmed", "Confirmed"), ("unsubscribed", "Unsubscribed")], default="pending", max_length=12)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("confirmation_sent_at", models.DateTimeField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("unsubscribed_at", models.DateTimeField(blank=True, null=True)),
                ("newsletter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="newsletters.newsletter")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["newsletter", "status"], name="newsletters_newslet_92c980_idx"),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(fields=("newsletter", "email"), name="unique_email_per_newsletter"),
        ),
        migrations.CreateModel(
            name="Issue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=200)),
                ("preheader", models.CharField(blank=True, help_text="The short preview text shown next to the subject in most inboxes.", max_length=200)),
                ("body", models.TextField(help_text="Markdown is supported.")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("scheduled", "Scheduled"), ("sending", "Sending"), ("sent", "Sent")], db_index=True, default="draft", max_length=10)),
                ("publish_to_web", models.BooleanField(default=True, help_text="Show this issue in the public archive after it is sent.", verbose_name="publish on the web")),
                ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("sending_started_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("recipients_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("newsletter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="issues", to="newsletters.newsletter")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(fields=["status", "scheduled_at"], name="newsletters_status_168727_idx"),
        ),
        migrations.CreateModel(
            name="Delivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=8)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="newsletters.issue")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="newsletters.subscription")),
            ],
            options={"verbose_name_plural": "deliveries"},
        ),
        migrations.AddConstraint(
            model_name="delivery",
            constraint=models.UniqueConstraint(fields=("issue", "subscription"), name="one_delivery_per_recipient"),
        ),
    ]
