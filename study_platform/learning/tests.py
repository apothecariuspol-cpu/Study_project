from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Lesson,
    Student,
    StudentAccess,
    StudentLessonProgress,
    Subject,
    TeacherCollection,
    TeacherCollectionFile,
    Topic,
)
from .views import generate_daily_lessons


class DailyPlanGeneratorTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(title="История")
        self.student = Student.objects.create(name="Тестовый ученик", exam="EGE")
        self.student.subjects.add(self.subject)
        self.topic = Topic.objects.create(subject=self.subject, title="Древняя Русь")

    def make_lesson(self, title, order, special_category="", is_published=True):
        return Lesson.objects.create(
            topic=self.topic,
            title=title,
            order=order,
            special_category=special_category,
            is_published=is_published,
        )

    def test_special_lesson_is_not_added_twice_when_it_is_next_in_sequence(self):
        first = self.make_lesson("Первый урок", 1)
        special = self.make_lesson("Культура", 2, special_category="culture")
        self.make_lesson("Третий урок", 3)
        StudentLessonProgress.objects.create(
            student=self.student,
            lesson=first,
            is_started=True,
            last_worked_at=timezone.now(),
        )

        result = generate_daily_lessons(self.student, self.subject, count=3)

        result_ids = [lesson.id for lesson in result]
        self.assertEqual(len(result_ids), len(set(result_ids)))
        self.assertEqual(result_ids.count(special.id), 1)

    def test_random_mode_uses_random_sample_and_respects_requested_count(self):
        lessons = [self.make_lesson("Урок %s" % number, number) for number in range(1, 6)]
        expected = lessons[-3:]

        with patch("learning.views.random.sample", return_value=expected) as sample:
            result = generate_daily_lessons(
                self.student, self.subject, count=3, mode="random"
            )

        sample.assert_called_once()
        self.assertEqual(result, expected)

    def test_random_mode_only_uses_published_lessons(self):
        published = [self.make_lesson("Опубликованный %s" % number, number) for number in range(1, 4)]
        self.make_lesson("Черновик", 4, is_published=False)

        with patch("learning.views.random.sample", side_effect=lambda population, count: list(population)[:count]):
            result = generate_daily_lessons(
                self.student, self.subject, count=3, mode="random"
            )

        self.assertEqual(set(result), set(published))


class TeacherCollectionDisplayTests(TestCase):
    def test_cabinet_shows_collection_description_and_download_links(self):
        subject = Subject.objects.create(title="История")
        student = Student.objects.create(name="Тестовый ученик", exam="EGE")
        student.subjects.add(subject)
        access = StudentAccess(student=student, code_lookup="test-lookup", code_hash="test-hash")
        access.save()

        collection = TeacherCollection.objects.create(
            title="Материалы к уроку",
            description="Дополнительные материалы для повторения.",
            subject=subject,
            is_active=True,
        )
        collection.students.add(student)
        material = TeacherCollectionFile.objects.create(
            collection=collection,
            file="teacher_collections/test/cards.pdf",
            description="Карточки для повторения",
        )

        session = self.client.session
        session["student_id"] = student.id
        session.save()

        response = self.client.get(reverse("cabinet"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дополнительные материалы для повторения.")
        self.assertContains(response, "Карточки для повторения")
        self.assertContains(response, reverse("download_teacher_collection_file", args=[material.id]))
