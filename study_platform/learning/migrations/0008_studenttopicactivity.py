from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0007_teachercollection"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentTopicActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("open_count", models.PositiveIntegerField(default=0, verbose_name="Количество открытий")),
                ("total_seconds", models.PositiveIntegerField(default=0, verbose_name="Время изучения, секунд")),
                ("last_opened_at", models.DateTimeField(blank=True, null=True, verbose_name="Последнее открытие")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="topic_activity", to="learning.student", verbose_name="Ученик")),
                ("topic", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_activity", to="learning.topic", verbose_name="Тема")),
            ],
            options={
                "verbose_name": "Активность ученика по теме",
                "verbose_name_plural": "Активность учеников по темам",
                "ordering": ["-open_count", "-total_seconds", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="studenttopicactivity",
            constraint=models.UniqueConstraint(fields=("student", "topic"), name="unique_student_topic_activity"),
        ),
    ]
