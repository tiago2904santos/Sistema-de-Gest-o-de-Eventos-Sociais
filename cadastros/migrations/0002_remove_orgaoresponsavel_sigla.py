from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="orgaoresponsavel",
            name="sigla",
        ),
    ]
