
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

