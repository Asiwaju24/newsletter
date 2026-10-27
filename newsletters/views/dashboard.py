import csv
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services
from ..forms import IssueForm, NewsletterForm, ScheduleForm, TestSendForm
from ..models import Delivery, Issue, Newsletter, Subscription
from ..rendering import render_markdown


# --- Ownership helpers --------------------------------------------------------
# Every object is looked up through the signed-in user, so other people's data
# simply doesn't exist as far as these views are concerned (404, not 403).

def _newsletter_for(request, pk) -> Newsletter:
    return get_object_or_404(Newsletter, pk=pk, owner=request.user)


def _issue_for(request, pk) -> Issue:
    return get_object_or_404(Issue.objects.select_related("newsletter"), pk=pk, newsletter__owner=request.user)


# --- Overview ------------------------------------------------------------------

@login_required
def dashboard(request):
    S = Subscription.Status
    newsletters = (
        Newsletter.objects.filter(owner=request.user)
        .annotate(
            confirmed_count=Count("subscriptions", filter=Q(subscriptions__status=S.CONFIRMED), distinct=True),
            sent_count=Count("issues", filter=Q(issues__status=Issue.Status.SENT), distinct=True),
        )
    )
    last_30 = timezone.now() - timedelta(days=30)
    subs = Subscription.objects.filter(newsletter__owner=request.user)
    stats = {
        "newsletters": newsletters.count(),
        "subscribers": subs.confirmed().count(),
        "new_subscribers": subs.confirmed().filter(confirmed_at__gte=last_30).count(),
        "issues_sent": Issue.objects.filter(newsletter__owner=request.user, status=Issue.Status.SENT).count(),
    }
    upcoming = (
        Issue.objects.filter(newsletter__owner=request.user, status=Issue.Status.SCHEDULED)
        .select_related("newsletter").order_by("scheduled_at")[:5]
    )
    return render(request, "newsletters/dashboard.html", {"newsletters": newsletters, "stats": stats, "upcoming": upcoming})


@login_required
@require_POST
def markdown_preview(request):
    return JsonResponse({"html": render_markdown(request.POST.get("text", ""))})


# --- Newsletters ---------------------------------------------------------------

@login_required
def newsletter_create(request):
    form = NewsletterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        newsletter = form.save(commit=False)
        newsletter.owner = request.user
        newsletter.save()
        messages.success(request, f"“{newsletter.title}” is ready. Now write your first email.")
        return redirect("issue_create", pk=newsletter.pk)
    return render(request, "newsletters/newsletter_form.html", {"form": form, "creating": True})


@login_required
def newsletter_manage(request, pk):
    newsletter = _newsletter_for(request, pk)
    S = Subscription.Status
    counts = {row["status"]: row["n"] for row in newsletter.subscriptions.values("status").annotate(n=Count("id"))}
    issues = newsletter.issues.annotate(
        failed_count=Count("deliveries", filter=Q(deliveries__status=Delivery.Status.FAILED)),
    )
    return render(request, "newsletters/newsletter_manage.html", {
        "newsletter": newsletter,
        "issues": issues,
        "confirmed": counts.get(S.CONFIRMED, 0),
        "pending": counts.get(S.PENDING, 0),
        "unsubscribed": counts.get(S.UNSUBSCRIBED, 0),
        "public_url": f"{settings.SITE_URL}{newsletter.get_absolute_url()}",
    })


@login_required
def newsletter_settings(request, pk):
    newsletter = _newsletter_for(request, pk)
    form = NewsletterForm(request.POST or None, instance=newsletter)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect("newsletter_manage", pk=newsletter.pk)
    return render(request, "newsletters/newsletter_form.html", {"form": form, "newsletter": newsletter, "creating": False})


@login_required
def newsletter_delete(request, pk):
    newsletter = _newsletter_for(request, pk)
    if request.method == "POST":
        title = newsletter.title
        newsletter.delete()
        messages.success(request, f"“{title}” and everything in it was deleted.")
        return redirect("dashboard")
    return render(request, "newsletters/confirm_delete.html", {
        "newsletter": newsletter,
        "heading": f"Delete “{newsletter.title}”?",
        "detail": "This permanently deletes the newsletter, every email in it, and its whole subscriber list. This can't be undone.",
        "cancel_url": reverse("newsletter_settings", args=[newsletter.pk]),
    })


# --- Subscribers -----------------------------------------------------------------

@login_required
def subscriber_list(request, pk):
    newsletter = _newsletter_for(request, pk)
    subscriptions = newsletter.subscriptions.all()
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if status in Subscription.Status.values:
        subscriptions = subscriptions.filter(status=status)
    if query:
        subscriptions = subscriptions.filter(email__icontains=query)
    page = Paginator(subscriptions, 50).get_page(request.GET.get("page"))
    params = {k: v for k, v in {"q": query, "status": status}.items() if v}
    return render(request, "newsletters/subscriber_list.html", {
        "newsletter": newsletter, "page": page, "status": status, "query": query,
        "pagination_qs": f"{urlencode(params)}&" if params else "",
        "statuses": Subscription.Status.choices,
    })


@login_required
def subscriber_export(request, pk):
    newsletter = _newsletter_for(request, pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{newsletter.slug}-subscribers.csv"'
    writer = csv.writer(response)
    writer.writerow(["email", "status", "subscribed_at", "confirmed_at", "unsubscribed_at"])
    for sub in newsletter.subscriptions.order_by("created_at"):
        writer.writerow([
            _csv_safe(sub.email), sub.status, sub.created_at.isoformat(),
            sub.confirmed_at.isoformat() if sub.confirmed_at else "",
            sub.unsubscribed_at.isoformat() if sub.unsubscribed_at else "",
        ])
    return response


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    return f"'{value}" if value[:1] in {"=", "+", "-", "@"} else value


@login_required
@require_POST
def subscriber_remove(request, pk, sub_pk):
    newsletter = _newsletter_for(request, pk)
    subscription = get_object_or_404(Subscription, pk=sub_pk, newsletter=newsletter)
    subscription.delete()
    messages.success(request, f"Removed {subscription.email}.")
    return redirect("subscriber_list", pk=newsletter.pk)


# --- Issues ----------------------------------------------------------------------

@login_required
def issue_create(request, pk):
    newsletter = _newsletter_for(request, pk)
    form = IssueForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue = form.save(commit=False)
        issue.newsletter = newsletter
        issue.save()
        messages.success(request, "Draft saved.")
        return redirect("issue_detail", pk=issue.pk)
    return render(request, "newsletters/issue_form.html", {"form": form, "newsletter": newsletter, "creating": True})


@login_required
def issue_edit(request, pk):
    issue = _issue_for(request, pk)
    if not issue.is_editable:
        messages.error(request, "This email has already been sent, so it can't be edited.")
        return redirect("issue_detail", pk=issue.pk)
    form = IssueForm(request.POST or None, instance=issue)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect("issue_detail", pk=issue.pk)
    return render(request, "newsletters/issue_form.html", {"form": form, "newsletter": issue.newsletter, "issue": issue, "creating": False})


@login_required
def issue_detail(request, pk):
    issue = _issue_for(request, pk)
    D = Delivery.Status
    counts = {row["status"]: row["n"] for row in issue.deliveries.values("status").annotate(n=Count("id"))}
    return render(request, "newsletters/issue_detail.html", {
        "issue": issue,
        "newsletter": issue.newsletter,
        "recipients": issue.newsletter.subscriptions.confirmed().count(),
        "delivered": counts.get(D.SENT, 0),
        "failed": counts.get(D.FAILED, 0),
        "skipped": counts.get(D.SKIPPED, 0),
        "test_form": TestSendForm(initial={"email": request.user.email}),
        "schedule_form": ScheduleForm(),
        "inline_sending": settings.NEWSLETTER_SEND_INLINE,
    })


@login_required
def issue_delete(request, pk):
    issue = _issue_for(request, pk)
    if issue.status in {Issue.Status.SENDING}:
        messages.error(request, "This email is being sent right now.")
        return redirect("issue_detail", pk=issue.pk)
    if request.method == "POST":
        newsletter_pk = issue.newsletter_id
        issue.delete()
        messages.success(request, "Email deleted.")
        return redirect("newsletter_manage", pk=newsletter_pk)
    return render(request, "newsletters/confirm_delete.html", {
        "newsletter": issue.newsletter,
        "heading": f"Delete “{issue.subject}”?",
        "detail": "The email and its results will be removed. Emails that were already sent can't be taken back.",
        "cancel_url": reverse("issue_detail", args=[issue.pk]),
    })


@login_required
@require_POST
def issue_action(request, pk):
    issue = _issue_for(request, pk)
    action = request.POST.get("action", "")
    S = Issue.Status

    def back():
        return redirect("issue_detail", pk=issue.pk)

    if action == "test":
        form = TestSendForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please enter a valid email address for the test.")
            return back()
        try:
            services.send_test(issue, form.cleaned_data["email"])
        except Exception:
            messages.error(request, "The test email couldn't be sent. Check your email settings and try again.")
        else:
            messages.success(request, f"Test sent to {form.cleaned_data['email']}.")
        return back()

    if action in {"send_now", "schedule"}:
        if issue.status not in {S.DRAFT, S.SCHEDULED}:
            messages.error(request, "This email has already been sent.")
            return back()
        if not issue.newsletter.subscriptions.confirmed().exists():
            messages.error(request, "Nobody has subscribed yet, so there's no one to send this to.")
            return back()
        if action == "schedule":
            form = ScheduleForm(request.POST)
            if not form.is_valid():
                messages.error(request, " ".join(form.errors["scheduled_at"]) if "scheduled_at" in form.errors else "Enter a valid date and time.")
                return back()
            services.schedule_issue(issue, form.cleaned_data["scheduled_at"])
            messages.success(request, "Scheduled. It will go out at the time you picked.")
            return back()
        services.schedule_issue(issue)
        if settings.NEWSLETTER_SEND_INLINE:
            result = services.send_issue(issue)
            if result:
                messages.success(request, f"Sent to {result.sent} subscriber{'s' if result.sent != 1 else ''}."
                                 + (f" {result.failed} didn't go through." if result.failed else ""))
        else:
            messages.success(request, "Done. It will go out within a minute or two.")
        return back()

    if action == "unschedule":
        if issue.status == S.SCHEDULED:
            services.unschedule_issue(issue)
            messages.success(request, "Cancelled. It's back in your drafts.")
        return back()

    if action == "retry":
        if services.retry_failed(issue):
            if settings.NEWSLETTER_SEND_INLINE:
                services.send_issue(issue)
                messages.success(request, "Tried again for the emails that failed.")
            else:
                messages.success(request, "Done. We'll try the failed ones again shortly.")
        return back()

    messages.error(request, "Unknown action.")
    return back()
