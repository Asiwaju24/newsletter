from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("newsletters", "0003_backfill_slugs_and_subscriptions")]

    operations = [
        migrations.AlterField(
            model_name="newsletter", name="slug",
            field=models.SlugField(blank=True, editable=False, max_length=80, unique=True),
        ),
        migrations.DeleteModel(name="Subscriber"),
    ]
