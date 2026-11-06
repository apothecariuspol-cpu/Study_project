
import hashlib
import hmac

from django.conf import settings
from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class Subject(models.Model):
    title = models.CharField("Название предмета", max_length=100)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"

    def __str__(self):
        return self.title


class Topic(models.Model):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="topics",
        verbose_name="Предмет"
    )
    title = models.CharField("Название темы", max_length=200)
    description = models.TextField("Краткое описание", blank=True)
    period = models.CharField("Период", max_length=100, blank=True)
    hashtags = models.CharField("Хештеги", max_length=300, blank=True,
                                help_text="Укажи через пробел, например: #ДревняяРусь #Князья")
    completion_percent = models.PositiveSmallIntegerField("Выполнение, %", default=0)
    theory_percent = models.PositiveSmallIntegerField("Теория, %", default=0)
    practice_percent = models.PositiveSmallIntegerField("Практика, %", default=0)
    correct_percent = models.PositiveSmallIntegerField("Верных ответов, %", default=0)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Тема"
        verbose_name_plural = "Темы"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.subject.title} — {self.title}"


class Lesson(models.Model):
    SPECIAL_CATEGORY_CHOICES = [
        ("", "Обычная подтема"),
        ("culture", "Культура"),
        ("maps", "Разборы на карте"),
    ]

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="Тематический блок"
    )
    title = models.CharField("Название подтемы", max_length=200)
    description = models.TextField("Краткое описание", blank=True)
    content = models.TextField("Теория", blank=True)
    completion_percent = models.PositiveSmallIntegerField("Выполнение, %", default=0)
    order = models.PositiveIntegerField("Порядок", default=0)
    is_published = models.BooleanField("Опубликована", default=False)
    special_category = models.CharField(
        "Особая категория",
        max_length=20,
        choices=SPECIAL_CATEGORY_CHOICES,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Подтема"
        verbose_name_plural = "Подтемы"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class MicroTopic(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="microtopics",
        verbose_name="Подтема",
    )
    title = models.CharField("Название микротемы", max_length=200)
    content = models.TextField("Материал", blank=True)
    completion_percent = models.PositiveSmallIntegerField("Выполнение, %", default=0)
    order = models.PositiveIntegerField("Порядок", default=0)
    is_published = models.BooleanField("Опубликована", default=False)

    class Meta:
        verbose_name = "Микротема"
        verbose_name_plural = "Микротемы"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.lesson.title} — {self.title}"


class Student(models.Model):
    EXAM_CHOICES = [
        ("OGE", "ОГЭ"),
        ("EGE", "ЕГЭ"),
    ]

    name = models.CharField("Имя ученика", max_length=150)
    exam = models.CharField(
        "Экзамен",
        max_length=3,
        choices=EXAM_CHOICES
    )
    subjects = models.ManyToManyField(
        Subject,
        verbose_name="Предметы",
        related_name="students"
    )
    is_demo = models.BooleanField("Демонстрационный аккаунт", default=False)

    class Meta:
        verbose_name = "Ученик"
        verbose_name_plural = "Ученики"

    def __str__(self):
        return self.name




class StudentAccess(models.Model):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="access",
        verbose_name="Ученик"
    )
    code_lookup = models.CharField(
        "Идентификатор кода",
        max_length=64,
        unique=True,
        editable=False
    )
    code_hash = models.CharField(
        "Защищённый код",
        max_length=128,
        editable=False
    )
    is_active = models.BooleanField("Доступ включён", default=True)

    class Meta:
        verbose_name = "Доступ ученика"
        verbose_name_plural = "Доступы учеников"

    def set_code(self, raw_code):
        normalized_code = raw_code.strip().upper()

        self.code_lookup = hmac.new(
            settings.SECRET_KEY.encode(),
            normalized_code.encode(),
            hashlib.sha256
        ).hexdigest()

        self.code_hash = make_password(normalized_code)

    def check_code(self, raw_code):
        normalized_code = raw_code.strip().upper()
        return check_password(normalized_code, self.code_hash)

    def __str__(self):
        return f"Доступ: {self.student.name}"



class StudentLessonProgress(models.Model):
    """Персональный прогресс ученика по уроку."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="lesson_progress",
        verbose_name="Ученик",
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="student_progress",
        verbose_name="Урок",
    )
    is_started = models.BooleanField("Начат", default=False)
    is_completed = models.BooleanField("Завершён", default=False)
    error_count = models.PositiveIntegerField("Количество ошибок", default=0)
    first_started_at = models.DateTimeField("Впервые начат", null=True, blank=True)
    last_worked_at = models.DateTimeField("Последняя работа", null=True, blank=True)
    last_recommended_at = models.DateTimeField("Последняя рекомендация", null=True, blank=True)
    completed_at = models.DateTimeField("Завершён", null=True, blank=True)

    class Meta:
        verbose_name = "Прогресс ученика по уроку"
        verbose_name_plural = "Прогресс учеников по урокам"
        constraints = [
            models.UniqueConstraint(fields=("student", "lesson"), name="unique_student_lesson_progress"),
        ]
        ordering = ["-last_worked_at", "id"]

    def __str__(self):
        return f"{self.student.name} — {self.lesson.title}"


class StudentTopicActivity(models.Model):
    """Персональная статистика открытия и времени изучения темы."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="topic_activity", verbose_name="Ученик"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="student_activity", verbose_name="Тема"
    )
    open_count = models.PositiveIntegerField("Количество открытий", default=0)
    total_seconds = models.PositiveIntegerField("Время изучения, секунд", default=0)
    last_opened_at = models.DateTimeField("Последнее открытие", null=True, blank=True)

    class Meta:
        verbose_name = "Активность ученика по теме"
        verbose_name_plural = "Активность учеников по темам"
        constraints = [
            models.UniqueConstraint(fields=("student", "topic"), name="unique_student_topic_activity"),
        ]
        ordering = ["-open_count", "-total_seconds", "id"]

    def __str__(self):
        return f"{self.student.name} — {self.topic.title}"


class StudentBestResult(models.Model):
    """Лучшее зафиксированное прохождение ученика по предмету."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="best_results", verbose_name="Ученик"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="student_best_results", verbose_name="Предмет"
    )
    best_date = models.DateField("Дата лучшего прохождения")
    theory_topics = models.PositiveIntegerField("Пройдено тем теории", default=0)
    practice_exercises = models.PositiveIntegerField("Выполнено упражнений", default=0)
    correct_answers = models.PositiveIntegerField("Правильных ответов", default=0)

    class Meta:
        verbose_name = "Лучший результат ученика"
        verbose_name_plural = "Лучшие результаты учеников"
        constraints = [
            models.UniqueConstraint(fields=("student", "subject"), name="unique_student_subject_best_result"),
        ]
        ordering = ["-best_date", "id"]

    def __str__(self):
        return f"{self.student.name} — {self.subject.title}: {self.best_date}"

class TeacherCollection(models.Model):
    """Общая подборка преподавателя, назначаемая нескольким ученикам."""

    title = models.CharField("Название подборки", max_length=200)
    description = models.TextField("Описание", blank=True)
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teacher_collections", verbose_name="Предмет",
        help_text="Если предмет не выбран, подборка показывается во всех предметах ученика.",
    )
    students = models.ManyToManyField(
        Student, related_name="teacher_collections", verbose_name="Назначить ученикам", blank=True
    )
    is_active = models.BooleanField("Показывать ученикам", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        verbose_name = "Подборка преподавателя"
        verbose_name_plural = "Подборки преподавателя"
        ordering = ["-updated_at", "title"]

    def __str__(self):
        return self.title


class TeacherCollectionFile(models.Model):
    """Файл с подписью внутри подборки преподавателя."""

    collection = models.ForeignKey(
        TeacherCollection, on_delete=models.CASCADE, related_name="materials",
        verbose_name="Подборка",
    )
    file = models.FileField("Файл", upload_to="teacher_collections/%Y/%m/")
    description = models.CharField("Описание файла", max_length=250, blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Файл подборки"
        verbose_name_plural = "Файлы подборки"
        ordering = ["order", "id"]

    def __str__(self):
        return self.description or self.file.name.rsplit("/", 1)[-1]

