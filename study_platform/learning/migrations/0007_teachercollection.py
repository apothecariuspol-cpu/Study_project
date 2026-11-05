from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0006_studentbestresult"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherCollection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Название подборки")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("is_active", models.BooleanField(default=True, verbose_name="Показывать ученикам")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создана")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменена")),
                ("subject", models.ForeignKey(blank=True, help_text="Если предмет не выбран, подборка показывается во всех предметах ученика.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="teacher_collections", to="learning.subject", verbose_name="Предмет")),
                ("students", models.ManyToManyField(blank=True, related_name="teacher_collections", to="learning.student", verbose_name="Назначить ученикам")),
            ],
            options={
                "verbose_name": "Подборка преподавателя",
                "verbose_name_plural": "Подборки преподавателя",
                "ordering": ["-updated_at", "title"],
            },
        ),
        migrations.CreateModel(
            name="TeacherCollectionFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="teacher_collections/%Y/%m/", verbose_name="Файл")),
                ("description", models.CharField(blank=True, max_length=250, verbose_name="Описание файла")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, verbose_name="Загружен")),
                ("collection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materials", to="learning.teachercollection", verbose_name="Подборка")),
            ],
            options={
                "verbose_name": "Файл подборки",
                "verbose_name_plural": "Файлы подборки",
                "ordering": ["order", "id"],
            },
        ),
    ]
