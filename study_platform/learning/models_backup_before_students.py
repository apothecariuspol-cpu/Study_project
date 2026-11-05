
from django.db import models


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
        verbose_name="Предмет",
    )
    title = models.CharField("Название блока", max_length=200)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Тематический блок"
        verbose_name_plural = "Тематические блоки"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.subject.title} — {self.title}"


class Lesson(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="Тематический блок",
    )
    title = models.CharField("Название урока", max_length=200)
    content = models.TextField("Теория", blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    is_published = models.BooleanField("Опубликован", default=False)

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

