from django.contrib import admin

from .models import Delivery, Issue, Newsletter, Subscription


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "is_public", "accepting_subscribers", "created_at")
    list_filter = ("is_public", "accepting_subscribers")
    search_fields = ("title", "owner__username", "owner__email")
    readonly_fields = ("slug", "created_at", "updated_at")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "newsletter", "status", "created_at", "confirmed_at")
    list_filter = ("status", "newsletter")
    search_fields = ("email",)
    readonly_fields = ("token", "created_at", "confirmation_sent_at", "confirmed_at", "unsubscribed_at")


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0
    can_delete = False
    readonly_fields = ("subscription", "status", "error", "sent_at")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("subject", "newsletter", "status", "scheduled_at", "sent_at", "recipients_count")
    list_filter = ("status", "newsletter")
    search_fields = ("subject",)
    readonly_fields = ("sending_started_at", "sent_at", "recipients_count", "created_at", "updated_at")
    inlines = [DeliveryInline]
