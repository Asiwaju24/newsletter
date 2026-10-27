"""Business logic: subscribing, confirming, composing and sending issues."""
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Delivery, Issue, Newsletter, Subscription

logger = logging.getLogger(__name__)


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL}{path}"


def _from_address(newsletter: Newsletter) -> str:
    """Send from the platform's verified address, but show the newsletter's name."""
    _, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
    return formataddr((newsletter.sender_name, address))


# --- Subscribing -------------------------------------------------------------

def subscribe(newsletter: Newsletter, email: str) -> Subscription:
    """Start (or resume) a double opt-in subscription and email the confirmation link.

    Safe to call repeatedly: confirmed readers get no email, pending readers get a
    fresh confirmation (at most once every few minutes), and former readers must
    confirm again.
    """
    email = email.strip().lower()
    subscription, created = Subscription.objects.get_or_create(newsletter=newsletter, email=email)

    if subscription.status == Subscription.Status.CONFIRMED:
        return subscription
    if subscription.status == Subscription.Status.UNSUBSCRIBED:
        subscription.reset_to_pending()

    recently_sent = (
        subscription.confirmation_sent_at
        and timezone.now() - subscription.confirmation_sent_at < timedelta(minutes=5)
    )
    if created or not recently_sent:
        send_confirmation_email(subscription)
    return subscription


def send_confirmation_email(subscription: Subscription) -> None:
    newsletter = subscription.newsletter
    context = {
        "newsletter": newsletter,
        "confirm_url": absolute_url(reverse("subscription_confirm", args=[subscription.token])),
        "site_name": settings.SITE_NAME,
    }
    message = EmailMultiAlternatives(
        subject=f"Please confirm your email for {newsletter.title}",
        body=render_to_string("newsletters/email/confirm.txt", context),
        from_email=_from_address(newsletter),
        to=[subscription.email],
    )
    message.attach_alternative(render_to_string("newsletters/email/confirm.html", context), "text/html")
    message.send()
    Subscription.objects.filter(pk=subscription.pk).update(confirmation_sent_at=timezone.now())


# --- Composing ---------------------------------------------------------------

def build_issue_message(issue: Issue, subscription: Subscription, *, connection=None, subject_prefix: str = ""):
    newsletter = issue.newsletter
    unsubscribe_url = absolute_url(reverse("unsubscribe", args=[subscription.token]))
    context = {
        "issue": issue,
        "newsletter": newsletter,
        "body_html": issue.body_html,
        "body_markdown": issue.body,
        "web_url": absolute_url(issue.get_absolute_url()) if issue.is_public else "",
        "unsubscribe_url": unsubscribe_url,
        "site_name": settings.SITE_NAME,
    }
    message = EmailMultiAlternatives(
        subject=f"{subject_prefix}{issue.subject}",
        body=render_to_string("newsletters/email/issue.txt", context),
        from_email=_from_address(newsletter),
        to=[subscription.email],
        reply_to=[newsletter.reply_to_address] if newsletter.reply_to_address else None,
        headers={
            # RFC 2369 + RFC 8062/8058 one-click unsubscribe, required by Gmail/Yahoo for bulk senders.
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "List-ID": f"{newsletter.title} <{newsletter.slug}.{_host()}>",
            "Precedence": "bulk",
        },
        connection=connection,
    )
    message.attach_alternative(render_to_string("newsletters/email/issue.html", context), "text/html")
    return message


def _host() -> str:
    return settings.SITE_URL.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def send_test(issue: Issue, to_email: str) -> None:
    """Send a one-off preview of the issue; nothing is recorded against the issue."""
    preview = Subscription(newsletter=issue.newsletter, email=to_email, token=uuid.uuid4())
    build_issue_message(issue, preview, subject_prefix="[Test] ").send()


# --- Scheduling & sending ----------------------------------------------------

@dataclass
class SendResult:
    sent: int
    failed: int
    skipped: int


def schedule_issue(issue: Issue, when=None) -> Issue:
    issue.status = Issue.Status.SCHEDULED
    issue.scheduled_at = when or timezone.now()
    issue.save(update_fields=["status", "scheduled_at", "updated_at"])
    return issue


def unschedule_issue(issue: Issue) -> Issue:
    issue.status = Issue.Status.DRAFT
    issue.scheduled_at = None
    issue.save(update_fields=["status", "scheduled_at", "updated_at"])
    return issue


def due_issues():
    """Issues ready to go out: scheduled in the past, or a send that stalled."""
    now = timezone.now()
    stale = now - timedelta(minutes=settings.NEWSLETTER_STALE_SENDING_MINUTES)
    return Issue.objects.filter(
        Q(status=Issue.Status.SCHEDULED, scheduled_at__lte=now)
        | Q(status=Issue.Status.SENDING, sending_started_at__lt=stale)
    )


def send_issue(issue: Issue) -> SendResult | None:
    """Deliver an issue to every confirmed subscriber. Returns None if another worker owns it.

    Idempotent and resumable: each recipient gets a Delivery row, already-sent rows are
    never re-sent, and failed rows are retried on the next call.
    """
    now = timezone.now()
    stale = now - timedelta(minutes=settings.NEWSLETTER_STALE_SENDING_MINUTES)
    # Atomic claim so two workers can never send the same issue.
    claimed = Issue.objects.filter(pk=issue.pk).filter(
        Q(status=Issue.Status.SCHEDULED) | Q(status=Issue.Status.SENDING, sending_started_at__lt=stale)
    ).update(status=Issue.Status.SENDING, sending_started_at=now)
    if not claimed:
        return None
    issue.refresh_from_db()

    existing = set(issue.deliveries.values_list("subscription_id", flat=True))
    Delivery.objects.bulk_create(
        [
            Delivery(issue=issue, subscription=sub)
            for sub in issue.newsletter.subscriptions.confirmed()
            if sub.pk not in existing
        ],
        ignore_conflicts=True,
    )

    connection = get_connection()
    connection.open()
    try:
        queue = issue.deliveries.filter(
            status__in=[Delivery.Status.PENDING, Delivery.Status.FAILED]
        ).select_related("subscription")
        for delivery in queue.iterator(chunk_size=200):
            subscription = delivery.subscription
            if subscription.status != Subscription.Status.CONFIRMED:
                delivery.status = Delivery.Status.SKIPPED  # unsubscribed since the send began
                delivery.save(update_fields=["status"])
                continue
            try:
                build_issue_message(issue, subscription, connection=connection).send()
            except Exception as exc:  # one bad address must not stop the batch
                logger.warning("Delivery to %s failed: %s", subscription.email, exc)
                delivery.status = Delivery.Status.FAILED
                delivery.error = str(exc)[:500]
                delivery.save(update_fields=["status", "error"])
            else:
                delivery.status = Delivery.Status.SENT
                delivery.error = ""
                delivery.sent_at = timezone.now()
                delivery.save(update_fields=["status", "error", "sent_at"])
    finally:
        connection.close()

    counts = {
        row["status"]: row["n"]
        for row in issue.deliveries.values("status").annotate(n=Count("id"))
    }
    issue.status = Issue.Status.SENT
    issue.sent_at = timezone.now()
    issue.recipients_count = counts.get(Delivery.Status.SENT, 0)
    issue.save(update_fields=["status", "sent_at", "recipients_count", "updated_at"])
    return SendResult(
        sent=counts.get(Delivery.Status.SENT, 0),
        failed=counts.get(Delivery.Status.FAILED, 0),
        skipped=counts.get(Delivery.Status.SKIPPED, 0),
    )


def retry_failed(issue: Issue) -> bool:
    """Re-queue a sent issue so its failed deliveries are attempted again."""
    if issue.status != Issue.Status.SENT or not issue.deliveries.filter(status=Delivery.Status.FAILED).exists():
        return False
    schedule_issue(issue)
    return True
