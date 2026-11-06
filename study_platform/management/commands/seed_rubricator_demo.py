from django.core.management.base import BaseCommand
from learning.models import Subject, Topic, Lesson, MicroTopic


class Command(BaseCommand):
    help = "Добавляет демонстрационную структуру рубрикатора по истории Древней Руси."

    def handle(self, *args, **options):
        subject, _ = Subject.objects.get_or_create(
            title="История",
            defaults={"description": "Демонстрационный предмет для рубрикатора."},
        )

        topic, _ = Topic.objects.get_or_create(
            subject=subject,
            title="Древняя Русь",
            defaults={
                "description": "Образование Древнерусского государства, первые князья, устройство и развитие Руси.",
                "period": "IX–XV вв.",
                "hashtags": "#ДревняяРусь #Рюрик #КиевскаяРусь #ПервыеКнязья",
                "completion_percent": 49,
                "theory_percent": 28,
                "practice_percent": 66,
                "correct_percent": 49,
                "order": 1,
            },
        )

        structure = [
            (
                "Образование Древнерусского государства",
                1,
                [
                    "Призвание варягов",
                    "Рюрик",
                    "Олег",
                    "Объединение Новгорода и Киева",
                ],
            ),
            (
                "Первые князья и внутренняя политика",
                2,
                [
                    "Игорь",
                    "Ольга",
                    "Святослав",
                    "Владимир I",
                ],
            ),
            (
                "Формирование территории и управление Русью",
                3,
                [
                    "Полюдье и уроки",
                    "Дань и реформы Ольги",
                    "Княжеская власть",
                    "Племенные союзы",
                ],
            ),
            (
                "Крещение Руси",
                4,
                [
                    "Причины принятия христианства",
                    "Выбор веры",
                    "Крещение при Владимире",
                    "Последствия крещения",
                ],
            ),
        ]

        for lesson_title, order, micro_titles in structure:
            lesson, _ = Lesson.objects.get_or_create(
                topic=topic,
                title=lesson_title,
                defaults={
                    "description": f"Ключевые события и понятия раздела «{lesson_title}».",
                    "completion_percent": [35, 60, 13, 0][order - 1],
                    "order": order,
                    "is_published": False,
                },
            )

            for index, micro_title in enumerate(micro_titles, start=1):
                MicroTopic.objects.get_or_create(
                    lesson=lesson,
                    title=micro_title,
                    defaults={
                        "completion_percent": [0, 13, 10, 0][(index - 1) % 4],
                        "order": index,
                        "is_published": False,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Демонстрационная структура рубрикатора добавлена."
            )
        )