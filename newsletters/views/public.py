from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .. import services
from ..forms import SubscribeForm
from ..models import Issue, Newsletter, Subscription
from ..throttle import client_ip, is_limited


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def _public_newsletters():
    return (
        Newsletter.objects.filter(is_public=True, accepting_subscribers=True)
        .select_related("owner")
        .annotate(issue_count=Count("issues", filter=Q(issues__status=Issue.Status.SENT, issues__publish_to_web=True)))
    )


def home(request):
    featured = _public_newsletters().order_by("-issue_count", "-created_at")[:6]
    return render(request, "newsletters/home.html", {"featured": featured})


def discover(request):
    query = request.GET.get("q", "").strip()
    newsletters = _public_newsletters().order_by("title")
    if query:
        newsletters = newsletters.filter(Q(title__icontains=query) | Q(description__icontains=query))
    page = Paginator(newsletters, 12).get_page(request.GET.get("page"))
    qs = f"{urlencode({'q': query})}&" if query else ""
    return render(request, "newsletters/discover.html", {"page": page, "query": query, "pagination_qs": qs})


def newsletter_detail(request, slug):
    newsletter = get_object_or_404(Newsletter.objects.select_related("owner"), slug=slug)
    form = SubscribeForm()

    if request.method == "POST":
        form = SubscribeForm(request.POST)
        if not newsletter.accepting_subscribers:
            messages.error(request, "This newsletter isn't taking new readers right now.")
        elif is_limited(
            f"subscribe:{client_ip(request)}",
            settings.NEWSLETTER_SUBSCRIBE_LIMIT,
            settings.NEWSLETTER_SUBSCRIBE_WINDOW_SECONDS,
        ):
            messages.error(request, "Too many attempts. Please try again in a little while.")
        elif form.is_valid():
            # A filled honeypot is a bot: pretend it worked, do nothing.
            if not form.cleaned_data["website"]:
                services.subscribe(newsletter, form.cleaned_data["email"])
            return redirect("subscription_pending", slug=newsletter.slug)

    issues = newsletter.issues.filter(status=Issue.Status.SENT, publish_to_web=True).order_by("-sent_at")[:20]
    return render(request, "newsletters/newsletter_detail.html", {"newsletter": newsletter, "form": form, "issues": issues})


def subscription_pending(request, slug):
    newsletter = get_object_or_404(Newsletter, slug=slug)
    return render(request, "newsletters/subscription_pending.html", {"newsletter": newsletter})


def issue_public(request, slug, pk):
    issue = get_object_or_404(
        Issue.objects.select_related("newsletter__owner"),
        pk=pk, newsletter__slug=slug, status=Issue.Status.SENT, publish_to_web=True,
    )
    return render(request, "newsletters/issue_public.html", {"issue": issue, "newsletter": issue.newsletter, "form": SubscribeForm()})


def confirm_subscription(request, token):
    subscription = get_object_or_404(Subscription.objects.select_related("newsletter"), token=token)
    if subscription.status != Subscription.Status.CONFIRMED:
        subscription.confirm()
    return render(request, "newsletters/subscription_confirmed.html", {"newsletter": subscription.newsletter})


@csrf_exempt  # Token-authenticated and idempotent; mail clients POST here for one-click unsubscribe.
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    subscription = get_object_or_404(Subscription.objects.select_related("newsletter"), token=token)
    context = {"newsletter": subscription.newsletter, "subscription": subscription}
    if request.method == "POST":
        if subscription.status != Subscription.Status.UNSUBSCRIBED:
            subscription.unsubscribe()
        return render(request, "newsletters/unsubscribed.html", context)
    # GET never changes state, so link scanners can't unsubscribe people by accident.
    return render(request, "newsletters/unsubscribe_confirm.html", context)


def legacy_subscribe(request, newsletter_id):
    newsletter = get_object_or_404(Newsletter, pk=newsletter_id)
    return redirect(newsletter, permanent=True)
