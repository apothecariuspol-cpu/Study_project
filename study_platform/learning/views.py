
import hashlib
import hmac
import random
import json

from django.conf import settings
from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Subject, Topic, Lesson, MicroTopic, Student, StudentAccess, StudentLessonProgress, StudentTopicActivity, StudentBestResult, TeacherCollectionFile, TeacherCollection


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


def _session_ids(values):
    """Преобразует сохранённые в сессии ID в множество целых чисел."""
    result = set()
    for value in values or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result



def _current_student(request):
    """Возвращает активного ученика из текущей сессии."""
    student_id = request.session.get("student_id")
    if not student_id:
        return None
    return Student.objects.filter(
        id=student_id,
        access__is_active=True,
    ).first()


def _ordered_student_lessons(student, subject):
    return list(
        Lesson.objects.filter(
            topic__subject=subject,
            topic__subject__students=student,
            is_published=True,
        ).select_related("topic", "topic__subject").order_by(
            "topic__order", "topic_id", "order", "id"
        )
    )


def generate_daily_lessons(student, subject, count=0, mode="auto"):
    """Подбирает уроки: незавершённые, затем с ошибками, затем новые."""
    try:
        count = max(0, min(99, int(count)))
    except (TypeError, ValueError):
        count = 0
    if count == 0:
        return []

    lessons = _ordered_student_lessons(student, subject)
    if not lessons:
        return []

    progress_rows = {
        row.lesson_id: row
        for row in StudentLessonProgress.objects.filter(
            student=student, lesson__in=lessons
        )
    }

    unfinished = []
    with_errors = []
    new_lessons = []
    for lesson in lessons:
        progress = progress_rows.get(lesson.id)
        if progress and progress.is_started and not progress.is_completed:
            unfinished.append(lesson)
        elif progress and progress.error_count > 0:
            with_errors.append(lesson)
        elif not progress or (not progress.is_started and not progress.is_completed):
            new_lessons.append(lesson)

    if mode == "random":
        chooser = lambda items: random.sample(items, len(items)) if len(items) > 1 else items
        unfinished = chooser(unfinished)
        with_errors = chooser(with_errors)
        new_lessons = chooser(new_lessons)
    else:
        unfinished.sort(key=lambda lesson: (
            progress_rows[lesson.id].last_worked_at.timestamp()
            if progress_rows[lesson.id].last_worked_at else 0,
            lesson.topic.order, lesson.order, lesson.id,
        ))
        with_errors.sort(key=lambda lesson: (
            -progress_rows[lesson.id].error_count,
            progress_rows[lesson.id].last_worked_at.timestamp()
            if progress_rows[lesson.id].last_worked_at else 0,
            lesson.topic.order, lesson.order, lesson.id,
        ))

    chosen = []
    chosen_ids = set()
    for group in (unfinished, with_errors, new_lessons):
        for lesson in group:
            if lesson.id in chosen_ids:
                continue
            chosen.append(lesson)
            chosen_ids.add(lesson.id)
            if len(chosen) >= count:
                return chosen
    return chosen


def _student_plan_settings(request):
    """Настройки дневного плана в сессии, раздельно по предметам."""
    settings_by_subject = request.session.get("daily_plan_settings", {})
    return settings_by_subject if isinstance(settings_by_subject, dict) else {}


@require_POST
def save_daily_plan_settings(request):
    student = _current_student(request)
    if not student:
        return JsonResponse({"ok": False, "error": "Необходим вход."}, status=403)
    try:
        subject_id = int(request.POST.get("subject_id", ""))
        theory_count = max(0, min(99, int(request.POST.get("theory_count", "0"))))
        practice_count = max(0, min(99, int(request.POST.get("practice_count", "0"))))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные настройки плана."}, status=400)
    if not student.subjects.filter(id=subject_id).exists():
        return JsonResponse({"ok": False, "error": "Предмет недоступен."}, status=404)
    settings_by_subject = _student_plan_settings(request).copy()
    settings_by_subject[str(subject_id)] = {
        "theory": theory_count,
        "practice": practice_count,
    }
    request.session["daily_plan_settings"] = settings_by_subject
    request.session.modified = True
    return JsonResponse({"ok": True})


@require_POST
def save_mood(request):
    """Сохраняет выбранное настроение в сессии ученика."""
    if not request.session.get("student_id"):
        return JsonResponse({"ok": False, "error": "Необходим вход."}, status=403)

    mood = request.POST.get("mood", "").strip()
    if mood not in MOODS:
        return JsonResponse({"ok": False, "error": "Неизвестное настроение."}, status=400)

    request.session["student_mood"] = mood
    request.session.modified = True
    return JsonResponse({"ok": True, "mood": mood})

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
                # Приветствие показывается каждому ученику при каждом новом входе.
                request.session["show_demo_welcome"] = True

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
    # Флаг одноразовый: приветствие появляется после нового входа,
    # но не открывается повторно при обычном обновлении кабинета.
    show_demo_welcome = bool(request.session.pop("show_demo_welcome", False))

    student_subjects = list(student.subjects.all())
    plan_settings = _student_plan_settings(request)

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

    # Динамический счётчик ошибок и сохранённый лучший результат —
    # строго в рамках текущего ученика и конкретного предмета.
    for tab in tabs:
        subject = next(item for item in student_subjects if item.id == tab["subject_id"])
        saved_plan = plan_settings.get(str(subject.id), {})
        tab["plan_theory"] = int(saved_plan.get("theory", tab["plan_theory"]))
        tab["plan_practice"] = int(saved_plan.get("practice", tab["plan_practice"]))
        tab["assignments"] = (
            TeacherCollection.objects
            .filter(is_active=True, students=student)
            .filter(models.Q(subject__isnull=True) | models.Q(subject=subject))
            .prefetch_related("materials")
            .distinct()
        )
        error_rows = list(
            StudentLessonProgress.objects
            .filter(
                student=student,
                lesson__topic__subject=subject,
                error_count__gt=0,
            )
            .select_related("lesson")
            .order_by("-error_count", "-last_worked_at", "lesson__order", "lesson_id")[:5]
        )
        max_errors = max((row.error_count for row in error_rows), default=0)
        tab["mistakes"] = [
            {
                "title": row.lesson.title,
                "error_count": row.error_count,
                "bar_percent": round(row.error_count / max_errors * 100) if max_errors else 0,
            }
            for row in error_rows
        ]

        best = StudentBestResult.objects.filter(student=student, subject=subject).first()
        if best:
            tab["metrics"] = {
                "best_date": f"{best.best_date.day} {['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'][best.best_date.month]}",
                "topics": f"{best.theory_topics} тем",
                "exercises": f"{best.practice_exercises} упражнений",
                "correct": f"{best.correct_answers} верно",
            }

    # Кабинет формирует план независимо от ручного выбора на странице «Теория».
    plan_items_by_subject = {subject.id: [] for subject in student_subjects}
    daily_plan_subjects = []
    for subject in student_subjects:
        daily_plan_subjects.append({
            "id": subject.id,
            "title": subject.title,
            "items": plan_items_by_subject.get(subject.id, []),
            "is_selected": False,
        })

    context = {
        "user_name": student.name,
        "student": student,
        "show_demo_welcome": show_demo_welcome,
        "student_mood": request.session.get("student_mood", MOODS[0]),
        "moods": MOODS,
        "student_subjects": student_subjects,
        "streak": 0,
        "tabs": tabs,
        "daily_plan_subjects": daily_plan_subjects,
        "has_rubricator_selection": False,
        "rubricator_selection_mode": "auto",
    }

    return render(request, "learning/cabinet.html", context)


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
            submitted_subject_ids = [str(subject.id) for subject in subjects]

        allowed_subject_ids = list(
            student.subjects
            .filter(id__in=submitted_subject_ids)
            .values_list("id", flat=True)
        )

        if action == "choose":
            submitted_topic_ids = request.POST.getlist("topic_ids")
            submitted_lesson_ids = request.POST.getlist("lesson_ids")
            submitted_microtopic_ids = request.POST.getlist("microtopic_ids")

            valid_topic_ids = list(Topic.objects.filter(
                id__in=submitted_topic_ids,
                subject_id__in=allowed_subject_ids,
                subject__students=student,
            ).values_list("id", flat=True))

            valid_lesson_ids = list(Lesson.objects.filter(
                id__in=submitted_lesson_ids,
                topic__subject_id__in=allowed_subject_ids,
                topic__subject__students=student,
            ).values_list("id", flat=True))

            valid_microtopic_ids = list(MicroTopic.objects.filter(
                id__in=submitted_microtopic_ids,
                lesson__topic__subject_id__in=allowed_subject_ids,
                lesson__topic__subject__students=student,
            ).values_list("id", flat=True))

            if not (valid_topic_ids or valid_lesson_ids or valid_microtopic_ids):
                messages.warning(request, "Сначала выбери хотя бы одну тему.")
            else:
                request.session["rubricator_selection"] = {
                    "mode": "chosen",
                    "subject_ids": [str(item) for item in allowed_subject_ids],
                    "topic_ids": [str(item) for item in valid_topic_ids],
                    "lesson_ids": [str(item) for item in valid_lesson_ids],
                    "microtopic_ids": [str(item) for item in valid_microtopic_ids],
                }
                request.session.modified = True
                messages.success(request, "Выбор сохранён для ручного запуска.")

        elif action == "random":
            request.session["rubricator_selection"] = {
                "mode": "random",
                "subject_ids": [str(item) for item in allowed_subject_ids],
                "lesson_ids": [],
                "topic_ids": [],
                "microtopic_ids": [],
            }
            request.session.modified = True
            messages.success(request, "Сохранён режим случайного подбора.")

        return redirect("rubricator")

    plan_theory_counts = {
        str(subject.id): int(
            _student_plan_settings(request).get(str(subject.id), {}).get(
                "theory", 3 if "истор" in subject.title.lower() else 2 if "общ" in subject.title.lower() else 3
            )
        )
        for subject in subjects
    }

    # Статусы тем рассчитываются по фактическому прогрессу текущего ученика.
    topic_list = [topic for subject in subjects for topic in subject.topics.all()]
    lesson_progress = {
        row["lesson_id"]: row
        for row in StudentLessonProgress.objects.filter(
            student=student,
            lesson__topic__in=topic_list,
            lesson__is_published=True,
        ).values("lesson_id", "is_started", "is_completed")
    }
    for topic in topic_list:
        published_lessons = [
            lesson for lesson in topic.lessons.all() if lesson.is_published
        ]
        states = [lesson_progress.get(lesson.id) for lesson in published_lessons]
        if states and all(state and state["is_completed"] for state in states):
            topic.student_status = "full"
        elif any(state and (state["is_started"] or state["is_completed"]) for state in states):
            topic.student_status = "started"
        else:
            topic.student_status = ""

    activity_rows = StudentTopicActivity.objects.filter(
        student=student, topic__in=topic_list
    ).select_related("topic")
    activity_by_topic = {row.topic_id: row for row in activity_rows}

    # В верхней строке показываем темы, которые ученик чаще открывает
    # или на которых проводит больше времени. У каждой темы — её хештег.
    opened_topics = []
    for topic in topic_list:
        activity = activity_by_topic.get(topic.id)
        if not activity or not (activity.open_count or activity.total_seconds):
            continue
        tags = (topic.hashtags or "").split()
        label = tags[0] if tags else "#" + "".join(
            character for character in topic.title if character.isalnum()
        )
        if not label.startswith("#"):
            label = "#" + label
        opened_topics.append({
            "topic_id": topic.id,
            "subject_id": topic.subject_id,
            "label": label,
            "open_count": activity.open_count,
            "total_seconds": activity.total_seconds,
        })
    popular_topics = sorted(
        opened_topics,
        key=lambda item: (item["open_count"], item["total_seconds"]),
        reverse=True,
    )[:8]

    selection = request.session.get("rubricator_selection", {})
    has_saved_selection = bool(selection)
    selected_subject_ids = [str(item) for item in selection.get("subject_ids", [])]
    selected_topic_ids = [str(item) for item in selection.get("topic_ids", [])]
    selected_lesson_ids = [str(item) for item in selection.get("lesson_ids", [])]
    selected_microtopic_ids = [str(item) for item in selection.get("microtopic_ids", [])]

    context = {
        "student": student,
        "student_mood": request.session.get("student_mood", MOODS[0]),
        "subjects": subjects,
        "has_saved_selection": has_saved_selection,
        "selected_subject_ids": selected_subject_ids,
        "selected_topic_ids": selected_topic_ids,
        "selected_lesson_ids": selected_lesson_ids,
        "selected_microtopic_ids": selected_microtopic_ids,
        "plan_theory_counts": plan_theory_counts,
        "popular_topics": popular_topics,
    }
    return render(request, "learning/rubricator.html", context)


@require_POST
def track_topic_activity(request):
    """Сохраняет открытия темы и время, проведённое в раскрытом блоке."""
    student = _current_student(request)
    if not student:
        return JsonResponse({"ok": False}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        topic_id = int(payload.get("topic_id"))
        seconds = max(0, min(300, int(payload.get("seconds", 0))))
        opened = bool(payload.get("opened", False))
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)

    topic = Topic.objects.filter(
        id=topic_id,
        subject__students=student,
    ).first()
    if topic is None:
        return JsonResponse({"ok": False}, status=404)

    activity, _ = StudentTopicActivity.objects.get_or_create(
        student=student, topic=topic
    )
    update_fields = []
    if opened:
        activity.open_count += 1
        activity.last_opened_at = timezone.now()
        update_fields.extend(["open_count", "last_opened_at"])
    if seconds:
        activity.total_seconds += seconds
        update_fields.append("total_seconds")
    if update_fields:
        activity.save(update_fields=update_fields)

    return JsonResponse({"ok": True})


@require_POST
def start_daily_plan(request):
    """Запускает решение плана с первого урока из сформированного списка."""
    student = _current_student(request)
    if not student:
        return redirect("subject_list")

    mode = request.POST.get("mode", "auto").strip().lower()
    subject_ids = request.POST.getlist("subject_filter")
    if not subject_ids and request.POST.get("subject_id"):
        subject_ids = [request.POST.get("subject_id")]

    try:
        subject_id = int(subject_ids[0]) if subject_ids else None
    except (TypeError, ValueError):
        subject_id = None

    subject = student.subjects.filter(id=subject_id).first() if subject_id else None
    if subject is None:
        messages.warning(request, "Сначала выбери предмет для плана.")
        return redirect("rubricator")

    if mode in {"auto", "random"}:
        saved = _student_plan_settings(request).get(str(subject.id), {})
        default_count = 3 if "истор" in subject.title.lower() else 2 if "общ" in subject.title.lower() else 3
        count = request.POST.get("count", saved.get("theory", default_count))
        lessons = generate_daily_lessons(student, subject, count, mode=mode)
    else:
        topic_ids = request.POST.getlist("topic_ids")
        lesson_ids = request.POST.getlist("lesson_ids")
        microtopic_ids = request.POST.getlist("microtopic_ids")
        selected_lesson_ids = MicroTopic.objects.filter(
            id__in=microtopic_ids,
            lesson__topic__subject=subject,
            lesson__is_published=True,
        ).values_list("lesson_id", flat=True)
        lessons = Lesson.objects.filter(
            topic__subject=subject,
            topic__subject__students=student,
            is_published=True,
        ).filter(
            models.Q(topic_id__in=topic_ids)
            | models.Q(id__in=lesson_ids)
            | models.Q(id__in=selected_lesson_ids)
        ).select_related("topic").order_by("topic__order", "topic_id", "order", "id")

    first_lesson = lessons.first() if hasattr(lessons, "first") else (lessons[0] if lessons else None)
    if first_lesson is None:
        messages.warning(request, "В плане пока нет доступных опубликованных уроков.")
        return redirect("rubricator")

    return redirect("lesson_detail", lesson_id=first_lesson.id)


@require_POST
def generate_daily_plan(request):
    """Возвращает персонально подобранные уроки для выбранного предмета."""
    student = _current_student(request)
    if not student:
        return JsonResponse({"ok": False, "error": "Необходим вход."}, status=403)

    try:
        subject_id = int(request.POST.get("subject_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Не указан предмет."}, status=400)

    subject = student.subjects.filter(id=subject_id).first()
    if not subject:
        return JsonResponse({"ok": False, "error": "Предмет недоступен."}, status=404)

    mode = request.POST.get("mode", "auto").strip().lower()
    if mode not in {"auto", "random"}:
        return JsonResponse({"ok": False, "error": "Неизвестный режим подбора."}, status=400)

    lessons = generate_daily_lessons(
        student, subject, request.POST.get("count", 0), mode=mode
    )
    return JsonResponse({
        "ok": True,
        "items": [
            {"title": lesson.title, "parent": lesson.topic.title,
             "url": f"/lesson/{lesson.id}/"}
            for lesson in lessons
        ],
    })


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
    lesson = get_object_or_404(Lesson, id=lesson_id, is_published=True)
    student = _current_student(request)
    progress = None

    if student and student.subjects.filter(id=lesson.topic.subject_id).exists():
        progress, created = StudentLessonProgress.objects.get_or_create(
            student=student,
            lesson=lesson,
            defaults={
                "is_started": True,
                "first_started_at": timezone.now(),
                "last_worked_at": timezone.now(),
            },
        )
        if not created:
            progress.is_started = True
            if not progress.first_started_at:
                progress.first_started_at = timezone.now()
            progress.last_worked_at = timezone.now()
            progress.save(update_fields=["is_started", "first_started_at", "last_worked_at"])

    return render(
        request,
        "learning/lesson_detail.html",
        {"lesson": lesson, "progress": progress},
    )


@require_POST
def complete_lesson(request, lesson_id):
    student = _current_student(request)
    if not student:
        return redirect("subject_list")

    lesson = get_object_or_404(
        Lesson,
        id=lesson_id,
        is_published=True,
        topic__subject__students=student,
    )
    now = timezone.now()
    progress, _ = StudentLessonProgress.objects.get_or_create(
        student=student,
        lesson=lesson,
        defaults={"is_started": True, "first_started_at": now},
    )
    progress.is_started = True
    progress.is_completed = True
    progress.completed_at = now
    progress.last_worked_at = now
    if not progress.first_started_at:
        progress.first_started_at = now
    progress.save(update_fields=[
        "is_started", "is_completed", "completed_at",
        "first_started_at", "last_worked_at",
    ])
    messages.success(request, "Урок отмечен как завершённый.")
    return redirect("lesson_detail", lesson_id=lesson.id)


@require_POST
def record_lesson_error(request, lesson_id):
    """Точка интеграции для тренажёра: увеличивает счётчик ошибок по уроку."""
    student = _current_student(request)
    if not student:
        return JsonResponse({"ok": False, "error": "Необходим вход."}, status=403)

    lesson = get_object_or_404(
        Lesson,
        id=lesson_id,
        is_published=True,
        topic__subject__students=student,
    )
    now = timezone.now()
    progress, _ = StudentLessonProgress.objects.get_or_create(
        student=student,
        lesson=lesson,
        defaults={"is_started": True, "first_started_at": now},
    )
    progress.is_started = True
    progress.error_count += 1
    progress.last_worked_at = now
    progress.save(update_fields=["is_started", "error_count", "last_worked_at"])
    return JsonResponse({"ok": True, "error_count": progress.error_count})


def download_teacher_collection_file(request, file_id):
    """Отдаёт файл только ученику, которому назначена подборка."""
    student_id = request.session.get("student_id")
    if not student_id:
        raise Http404

    access = StudentAccess.objects.filter(
        student_id=student_id, is_active=True
    ).first()
    if access is None:
        raise Http404

    material = get_object_or_404(
        TeacherCollectionFile.objects.select_related("collection"),
        pk=file_id,
        collection__is_active=True,
        collection__students=access.student,
    )
    try:
        file_handle = material.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("Файл не найден")

    filename = material.file.name.rsplit("/", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)
