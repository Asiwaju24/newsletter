from django.db import migrations
from django.utils.text import slugify


def backfill(apps, schema_editor):
    Newsletter = apps.get_model("newsletters", "Newsletter")
    Subscriber = apps.get_model("newsletters", "Subscriber")
    Subscription = apps.get_model("newsletters", "Subscription")

    used = set()
    for newsletter in Newsletter.objects.order_by("id"):
        base = slugify(newsletter.title)[:70] or "newsletter"
        slug, n = base, 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        newsletter.slug = slug
        newsletter.save(update_fields=["slug"])

    # Legacy subscribers never went through confirmation: grandfather them in as confirmed.
    for subscriber in Subscriber.objects.all():
        email = subscriber.email.strip().lower()
        for newsletter in subscriber.newsletters.all():
            Subscription.objects.get_or_create(
                newsletter=newsletter, email=email, defaults={"status": "confirmed"},
            )


class Migration(migrations.Migration):

    dependencies = [("newsletters", "0002_platform_models")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
