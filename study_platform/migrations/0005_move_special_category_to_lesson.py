from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0004_studentlessonprogress_and_special_category"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="topic",
            name="special_category",
        ),
        migrations.AddField(
            model_name="lesson",
            name="special_category",
            field=models.CharField(
                blank=True,
                choices=[("", "Обычная подтема"), ("culture", "Культура"), ("maps", "Разборы на карте")],
                default="",
                max_length=20,
                verbose_name="Особая категория",
            ),
        ),
    ]
