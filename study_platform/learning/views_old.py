import hashlib
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import Subject, Topic, Lesson, MicroTopic, StudentAccess


MOODS = [
    "атакующий катафракт",
    "милосердный катафракт",
    "усталый медоед",
    "орущая чайка",
    "сонный енот",
    "тревожный голубь",
    "суровый барсук",
    "удивлённая капибара",
    "уставший филин",
    "боевой тушканчик",
]


@require_POST
def save_mood(request):
    """Сохраняет выбранное настроение ученика в сессии."""

    student_id = request.session.get("student_id")

    if not student_id:
        return JsonResponse(
            {"success": False, "error": "Необходима авторизация."},
            status=401,
        )

    mood = request.POST.get("mood", "").strip()

    if mood not in MOODS:
        return JsonResponse(
            {"success": False, "error": "Неизвестное настроение."},
            status=400,
        )

    request.session["student_mood"] = mood

    return JsonResponse({
        "success": True,
        "mood": mood,
    })


def _session_ids(values):
    """Преобразует сохранённые в сессии ID в множество целых чисел."""

    result = set()

    for value in values or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue

    return result


def subject_list(request):
    """Стартовая страница и вход ученика по персональному коду."""

    error = None

    if request.method == "POST":
        raw_code = request.POST.get("access_code", "").strip().upper()

        if not raw_code:
            error = "Введи персональный код."

        else:
            lookup = hmac.new(
                settings.SECRET_KEY.encode(),
                raw_code.encode(),
                hashlib.sha256,
            ).hexdigest()

            access = (
                StudentAccess.objects
                .select_related("student")
                .filter(code_lookup=lookup)
                .first()
            )

            if access is None or not access.check_code(raw_code):
                error = "Неверный код. Проверь его и попробуй ещё раз."

            elif not access.is_active:
                error = "Доступ к платформе временно отключён."

            else:
                request.session.cycle_key()
                request.session["student_id"] = access.student_id
                request.session["student_mood"] = MOODS[0]

                # Приветствие показывается при каждом новом успешном входе в демо.
                request.session["show_demo_welcome"] = bool(
                    getattr(access.student, "is_demo", False)
                )

                return redirect("cabinet")

    return render(
        request,
        "learning/subject_list.html",
        {"login_error": error},
    )


def cabinet(request):
    """Личный кабинет авторизованного ученика."""

    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("subject_list")

    access = (
        StudentAccess.objects
        .select_related("student")
        .filter(student_id=student_id, is_active=True)
        .first()
    )

    if access is None:
        request.session.flush()
        return redirect("subject_list")

    student = access.student

    # Флаг одноразовый: после показа он удаляется.
    # Новый ввод демо-кода установит его снова.
    show_demo_welcome = bool(
        request.session.pop("show_demo_welcome", False)
    ) and bool(getattr(student, "is_demo", False))

    student_subjects = list(student.subjects.all())

    history = {
        "key": "history",
        "title": "История",
        "theory_percent": 0,
        "practice_percent": 0,
        "plan_theory": 3,
        "plan_practice": 12,
        "topics": [],
        "mistakes": [],
        "assignments": [],
        "weak_topics": [],
        "metrics": {},
        "trials": [],
    }

    society = {
        "key": "society",
        "title": "Общество",
        "theory_percent": 0,
        "practice_percent": 0,
        "plan_theory": 2,
        "plan_practice": 8,
        "topics": [],
        "mistakes": [],
        "assignments": [],
        "weak_topics": [],
        "metrics": {},
        "trials": [],
    }

    # Примерные данные для демонстрационного кабинета.
    if getattr(student, "is_demo", False):
        history["topics"] = [
            {
                "title": "Дмитрий Донской",
                "theory_percent": 54,
                "practice_done": 10,
                "practice_total": 12,
                "url": "/theory/",
            },
        ]

        society["topics"] = [
            {
                "title": "Социальные нормы",
                "theory_percent": 30,
                "practice_done": 3,
                "practice_total": 10,
                "url": "/theory/",
            },
        ]

    tabs = []

    for subject in student_subjects:
        title = subject.title.lower()

        if "истор" in title:
            tab = history.copy()
            tab["subject_id"] = subject.id
            tabs.append(tab)

        elif "общ" in title:
            tab = society.copy()
            tab["subject_id"] = subject.id
            tabs.append(tab)

    # Берём сохранённый выбор из рубрикатора и повторно проверяем,
    # что все ID относятся к предметам текущего ученика.
    selection = request.session.get("rubricator_selection", {})

    selected_subject_ids = _session_ids(selection.get("subject_ids"))
    allowed_subject_ids = {subject.id for subject in student_subjects}

    selected_subject_ids &= allowed_subject_ids

    selected_topic_ids = _session_ids(selection.get("topic_ids"))
    selected_lesson_ids = _session_ids(selection.get("lesson_ids"))
    selected_microtopic_ids = _session_ids(selection.get("microtopic_ids"))

    plan_items_by_subject = {
        subject.id: [] for subject in student_subjects
    }

    if selection.get("mode") == "chosen":

        selected_topics = list(
            Topic.objects
            .filter(
                id__in=selected_topic_ids,
                subject_id__in=allowed_subject_ids,
                subject__students=student,
            )
            .select_related("subject")
            .order_by("subject_id", "order", "id")
        )

        valid_topic_ids = {
            topic.id for topic in selected_topics
        }

        for topic in selected_topics:
            plan_items_by_subject[topic.subject_id].append({
                "title": topic.title,
                "parent": "",
            })

        selected_lessons = list(
            Lesson.objects
            .filter(
                id__in=selected_lesson_ids,
                topic__subject_id__in=allowed_subject_ids,
                topic__subject__students=student,
            )
            .exclude(topic_id__in=valid_topic_ids)
            .select_related("topic", "topic__subject")
            .order_by(
                "topic__subject_id",
                "topic__order",
                "order",
                "id",
            )
        )

        valid_lesson_ids = {
            lesson.id for lesson in selected_lessons
        }

        for lesson in selected_lessons:
            plan_items_by_subject[lesson.topic.subject_id].append({
                "title": lesson.title,
                "parent": lesson.topic.title,
            })

        selected_microtopics = (
            MicroTopic.objects
            .filter(
                id__in=selected_microtopic_ids,
                lesson__topic__subject_id__in=allowed_subject_ids,
                lesson__topic__subject__students=student,
            )
            .exclude(lesson_id__in=valid_lesson_ids)
            .exclude(lesson__topic_id__in=valid_topic_ids)
            .select_related(
                "lesson",
                "lesson__topic",
                "lesson__topic__subject",
            )
            .order_by(
                "lesson__topic__subject_id",
                "lesson__topic__order",
                "lesson__order",
                "order",
                "id",
            )
        )

        for microtopic in selected_microtopics:
            subject_id = microtopic.lesson.topic.subject_id

            plan_items_by_subject[subject_id].append({
                "title": microtopic.title,
                "parent": (
                    f"{microtopic.lesson.topic.title} / "
                    f"{microtopic.lesson.title}"
                ),
            })

    daily_plan_subjects = []

    for subject in student_subjects:
        daily_plan_subjects.append({
            "id": subject.id,
            "title": subject.title,
            "items": plan_items_by_subject.get(subject.id, []),
            "is_selected": subject.id in selected_subject_ids,
        })

    context = {
        "user_name": student.name,
        "student": student,
        "show_demo_welcome": show_demo_welcome,
        "student_mood": request.session.get(
            "student_mood",
            MOODS[0],
        ),
        "moods": MOODS,
        "student_subjects": student_subjects,
        "streak": 0,
        "tabs": tabs,
        "daily_plan_subjects": daily_plan_subjects,
        "has_rubricator_selection": bool(selection),
        "rubricator_selection_mode": selection.get("mode", ""),
    }

    return render(
        request,
        "learning/cabinet.html",
        context,
    )


def rubricator(request):
    """Рубрикатор теории для авторизованного ученика."""

    student_id = request.session.get("student_id")

    if not student_id:
        return redirect("subject_list")

    access = (
        StudentAccess.objects
        .select_related("student")
        .filter(student_id=student_id, is_active=True)
        .first()
    )

    if access is None:
        request.session.flush()
        return redirect("subject_list")

    student = access.student

    subjects = (
        student.subjects
        .prefetch_related("topics__lessons__microtopics")
        .all()
    )

    if request.method == "POST":

        action = request.POST.get("action", "choose")
        submitted_subject_ids = request.POST.getlist("subject_filter")

        if not submitted_subject_ids:
            submitted_subject_ids = [
                str(subject.id) for subject in subjects
            ]

        allowed_subject_ids = list(
            student.subjects
            .filter(id__in=submitted_subject_ids)
            .values_list("id", flat=True)
        )

        if action == "choose":

            submitted_topic_ids = request.POST.getlist("topic_ids")
            submitted_lesson_ids = request.POST.getlist("lesson_ids")
            submitted_microtopic_ids = request.POST.getlist(
                "microtopic_ids"
            )

            valid_topic_ids = list(
                Topic.objects.filter(
                    id__in=submitted_topic_ids,
                    subject_id__in=allowed_subject_ids,
                    subject__students=student,
                ).values_list("id", flat=True)
            )

            valid_lesson_ids = list(
                Lesson.objects.filter(
                    id__in=submitted_lesson_ids,
                    topic__subject_id__in=allowed_subject_ids,
                    topic__subject__students=student,
                ).values_list("id", flat=True)
            )

            valid_microtopic_ids = list(
                MicroTopic.objects.filter(
                    id__in=submitted_microtopic_ids,
                    lesson__topic__subject_id__in=allowed_subject_ids,
                    lesson__topic__subject__students=student,
                ).values_list("id", flat=True)
            )

            if not (
                valid_topic_ids
                or valid_lesson_ids
                or valid_microtopic_ids
            ):
                messages.warning(
                    request,
                    "Сначала выбери хотя бы одну тему.",
                )

            else:
                request.session["rubricator_selection"] = {
                    "mode": "chosen",
                    "subject_ids": [
                        str(item) for item in allowed_subject_ids
                    ],
                    "topic_ids": [
                        str(item) for item in valid_topic_ids
                    ],
                    "lesson_ids": [
                        str(item) for item in valid_lesson_ids
                    ],
                    "microtopic_ids": [
                        str(item) for item in valid_microtopic_ids
                    ],
                }

                request.session.modified = True

                messages.success(
                    request,
                    "Выбор сохранён. Он появится в дневном плане кабинета.",
                )

        elif action == "random":

            request.session["rubricator_selection"] = {
                "mode": "random",
                "subject_ids": [
                    str(item) for item in allowed_subject_ids
                ],
                "lesson_ids": [],
                "topic_ids": [],
                "microtopic_ids": [],
            }

            request.session.modified = True

            messages.success(
                request,
                "Сохранён режим случайного подбора.",
            )

        return redirect("rubricator")

    selection = request.session.get("rubricator_selection", {})

    has_saved_selection = bool(selection)

    selected_subject_ids = [
        str(item) for item in selection.get("subject_ids", [])
    ]

    selected_topic_ids = [
        str(item) for item in selection.get("topic_ids", [])
    ]

    selected_lesson_ids = [
        str(item) for item in selection.get("lesson_ids", [])
    ]

    selected_microtopic_ids = [
        str(item) for item in selection.get("microtopic_ids", [])
    ]

    context = {
        "student": student,
        "student_mood": request.session.get(
            "student_mood",
            MOODS[0],
        ),
        "subjects": subjects,
        "has_saved_selection": has_saved_selection,
        "selected_subject_ids": selected_subject_ids,
        "selected_topic_ids": selected_topic_ids,
        "selected_lesson_ids": selected_lesson_ids,
        "selected_microtopic_ids": selected_microtopic_ids,
    }

    return render(
        request,
        "learning/rubricator.html",
        context,
    )


def logout_student(request):
    """Выход ученика из личного кабинета."""

    request.session.flush()

    return redirect("subject_list")


def topic_list(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    topics = subject.topics.all()

    return render(
        request,
        "learning/topic_list.html",
        {
            "subject": subject,
            "topics": topics,
        },
    )


def lesson_detail(request, lesson_id):
    lesson = get_object_or_404(
        Lesson,
        id=lesson_id,
        is_published=True,
    )

    return render(
        request,
        "learning/lesson_detail.html",
        {"lesson": lesson},
    )