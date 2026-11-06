from datetime import date

from django.db import migrations, models
import django.db.models.deletion


def add_demo_best_results(apps, schema_editor):
    Student = apps.get_model("learning", "Student")
    Subject = apps.get_model("learning", "Subject")
    BestResult = apps.get_model("learning", "StudentBestResult")

    demo_students = Student.objects.filter(is_demo=True)
    for student in demo_students:
        for subject in Subject.objects.filter(students=student):
            BestResult.objects.get_or_create(
                student=student,
                subject=subject,
                defaults={
                    "best_date": date(2026, 10, 21),
                    "theory_topics": 3,
                    "practice_exercises": 32,
                    "correct_answers": 23,
                },
            )


class Migration(migrations.Migration):
    dependencies = [("learning", "0005_move_special_category_to_lesson")]

    operations = [
        migrations.CreateModel(
            name="StudentBestResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("best_date", models.DateField(verbose_name="Дата лучшего прохождения")),
                ("theory_topics", models.PositiveIntegerField(default=0, verbose_name="Пройдено тем теории")),
                ("practice_exercises", models.PositiveIntegerField(default=0, verbose_name="Выполнено упражнений")),
                ("correct_answers", models.PositiveIntegerField(default=0, verbose_name="Правильных ответов")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="best_results", to="learning.student", verbose_name="Ученик")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_best_results", to="learning.subject", verbose_name="Предмет")),
            ],
            options={"verbose_name": "Лучший результат ученика", "verbose_name_plural": "Лучшие результаты учеников", "ordering": ["-best_date", "id"]},
        ),
        migrations.AddConstraint(
            model_name="studentbestresult",
            constraint=models.UniqueConstraint(fields=("student", "subject"), name="unique_student_subject_best_result"),
        ),
        migrations.RunPython(add_demo_best_results, migrations.RunPython.noop),
    ]
