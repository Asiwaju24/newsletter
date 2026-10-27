from django.urls import path

from .views import dashboard, public

urlpatterns = [
    # Public site
    path("", public.home, name="home"),
    path("discover/", public.discover, name="discover"),
    path("n/<slug:slug>/", public.newsletter_detail, name="newsletter_detail"),
    path("n/<slug:slug>/check-your-inbox/", public.subscription_pending, name="subscription_pending"),
    path("n/<slug:slug>/issues/<int:pk>/", public.issue_public, name="issue_public"),
    path("subscriptions/confirm/<uuid:token>/", public.confirm_subscription, name="subscription_confirm"),
    path("subscriptions/unsubscribe/<uuid:token>/", public.unsubscribe, name="unsubscribe"),
    # Legacy URL from the first version of the project
    path("newsletters/subscribe/<int:newsletter_id>/", public.legacy_subscribe, name="legacy_subscribe"),
    # Dashboard
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("dashboard/preview/", dashboard.markdown_preview, name="markdown_preview"),
    path("dashboard/newsletters/new/", dashboard.newsletter_create, name="newsletter_create"),
    path("dashboard/newsletters/<int:pk>/", dashboard.newsletter_manage, name="newsletter_manage"),
    path("dashboard/newsletters/<int:pk>/settings/", dashboard.newsletter_settings, name="newsletter_settings"),
    path("dashboard/newsletters/<int:pk>/delete/", dashboard.newsletter_delete, name="newsletter_delete"),
    path("dashboard/newsletters/<int:pk>/subscribers/", dashboard.subscriber_list, name="subscriber_list"),
    path("dashboard/newsletters/<int:pk>/subscribers/export.csv", dashboard.subscriber_export, name="subscriber_export"),
    path("dashboard/newsletters/<int:pk>/subscribers/<int:sub_pk>/remove/", dashboard.subscriber_remove, name="subscriber_remove"),
    path("dashboard/newsletters/<int:pk>/issues/new/", dashboard.issue_create, name="issue_create"),
    path("dashboard/issues/<int:pk>/", dashboard.issue_detail, name="issue_detail"),
    path("dashboard/issues/<int:pk>/edit/", dashboard.issue_edit, name="issue_edit"),
    path("dashboard/issues/<int:pk>/delete/", dashboard.issue_delete, name="issue_delete"),
    path("dashboard/issues/<int:pk>/action/", dashboard.issue_action, name="issue_action"),
]
