import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Newsletter(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="newsletters")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True, blank=True, editable=False)
    description = models.TextField(max_length=1000)
    from_name = models.CharField(
        "sender name", max_length=80, blank=True,
        help_text="Shown as the sender in your readers' inboxes. Defaults to the newsletter title.",
    )
    reply_to = models.EmailField(
        "reply-to address", blank=True,
        help_text="Replies from readers go here. Defaults to your account email.",
    )
    is_public = models.BooleanField(
        "list in Discover", default=True,
        help_text="Unlisted newsletters can still be joined through their link.",
    )
    accepting_subscribers = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.title)[:70] or "newsletter"
        slug, n = base, 2
        while Newsletter.objects.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse("newsletter_detail", args=[self.slug])

    @property
    def sender_name(self) -> str:
        return self.from_name or self.title

    @property
    def reply_to_address(self) -> str:
        return self.reply_to or self.owner.email


class SubscriptionQuerySet(models.QuerySet):
    def confirmed(self):
        return self.filter(status=Subscription.Status.CONFIRMED)


class Subscription(models.Model):
    """One email address on one newsletter's list."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting to confirm"
        CONFIRMED = "confirmed", "Subscribed"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"

    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE, related_name="subscriptions")
    email = models.EmailField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["newsletter", "email"], name="unique_email_per_newsletter"),
        ]
        indexes = [models.Index(fields=["newsletter", "status"])]

    def __str__(self):
        return f"{self.email} → {self.newsletter}"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def confirm(self):
        self.status = self.Status.CONFIRMED
        self.confirmed_at = timezone.now()
        self.unsubscribed_at = None
        self.save(update_fields=["status", "confirmed_at", "unsubscribed_at"])

    def unsubscribe(self):
        self.status = self.Status.UNSUBSCRIBED
        self.unsubscribed_at = timezone.now()
        self.save(update_fields=["status", "unsubscribed_at"])

    def reset_to_pending(self):
        """Re-subscribing after unsubscribing requires confirming again."""
        self.status = self.Status.PENDING
        self.token = uuid.uuid4()
        self.unsubscribed_at = None
        self.confirmed_at = None
        self.save(update_fields=["status", "token", "unsubscribed_at", "confirmed_at"])


class Issue(models.Model):
    """A single edition of a newsletter."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"

    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE, related_name="issues")
    subject = models.CharField(max_length=200)
    preheader = models.CharField(
        max_length=200, blank=True,
        help_text="The short preview text shown next to the subject in most inboxes.",
    )
    body = models.TextField(help_text="Markdown is supported.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    publish_to_web = models.BooleanField(
        "publish on the web", default=True,
        help_text="Show this issue in the public archive after it is sent.",
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sending_started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipients_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"])]

    def __str__(self):
        return self.subject

    @property
    def is_editable(self) -> bool:
        return self.status in {self.Status.DRAFT, self.Status.SCHEDULED}

    @property
    def is_public(self) -> bool:
        return self.status == self.Status.SENT and self.publish_to_web

    def get_absolute_url(self):
        return reverse("issue_public", args=[self.newsletter.slug, self.pk])

    @property
    def body_html(self) -> str:
        from .rendering import render_markdown

        return render_markdown(self.body)


class Delivery(models.Model):
    """Per-recipient delivery record; makes sending resumable and auditable."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="deliveries")
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="deliveries")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "deliveries"
        constraints = [models.UniqueConstraint(fields=["issue", "subscription"], name="one_delivery_per_recipient")]

    def __str__(self):
        return f"{self.issue_id} → {self.subscription.email} ({self.status})"
