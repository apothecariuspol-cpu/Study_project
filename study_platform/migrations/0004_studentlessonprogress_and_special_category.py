# Generated for per-student lesson progress and explicit special topic categories.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("learning", "0003_alter_lesson_options_alter_topic_options_and_more")]

    operations = [
        migrations.AddField(
            model_name="topic",
            name="special_category",
            field=models.CharField(blank=True, choices=[("", "Обычный блок"), ("culture", "Культура"), ("maps", "Разборы на карте")], default="", max_length=20, verbose_name="Особая категория"),
        ),
        migrations.CreateModel(
            name="StudentLessonProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_started", models.BooleanField(default=False, verbose_name="Начат")),
                ("is_completed", models.BooleanField(default=False, verbose_name="Завершён")),
                ("error_count", models.PositiveIntegerField(default=0, verbose_name="Количество ошибок")),
                ("first_started_at", models.DateTimeField(blank=True, null=True, verbose_name="Впервые начат")),
                ("last_worked_at", models.DateTimeField(blank=True, null=True, verbose_name="Последняя работа")),
                ("last_recommended_at", models.DateTimeField(blank=True, null=True, verbose_name="Последняя рекомендация")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Завершён")),
                ("lesson", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_progress", to="learning.lesson", verbose_name="Урок")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lesson_progress", to="learning.student", verbose_name="Ученик")),
            ],
            options={"verbose_name": "Прогресс ученика по уроку", "verbose_name_plural": "Прогресс учеников по урокам", "ordering": ["-last_worked_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="studentlessonprogress",
            constraint=models.UniqueConstraint(fields=("student", "lesson"), name="unique_student_lesson_progress"),
        ),
    ]
