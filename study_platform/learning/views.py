
import hashlib
import hmac
import random

from django.conf import settings
from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.http import require_POST

from .models import Subject, Topic, Lesson, MicroTopic, Student, StudentAccess, StudentLessonProgress, StudentBestResult, TeacherCollectionFile, TeacherCollection


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


def generate_daily_lessons(student, subject, count=3, mode="auto"):
    """Подбирает уроки по четырём согласованным приоритетам."""
    try:
        count = max(1, min(20, int(count)))
    except (TypeError, ValueError):
        count = 3

    lessons = _ordered_student_lessons(student, subject)
    if not lessons:
        return []

    # Случайный режим не использует приоритеты персонального алгоритма.
    if mode == "random":
        return random.sample(lessons, min(count, len(lessons)))

    progress_rows = {
        row.lesson_id: row
        for row in StudentLessonProgress.objects.filter(
            student=student, lesson__in=lessons
        )
    }
    positions = {lesson.id: index for index, lesson in enumerate(lessons)}
    latest = max(
        (row for row in progress_rows.values() if row.last_worked_at),
        key=lambda row: row.last_worked_at,
        default=None,
    )

    # Приоритет 1: последовательное движение по рубрикатору после
    # последнего урока, с переходом к началу, если дошли до конца.
    start_index = positions.get(latest.lesson_id, -1) + 1 if latest else 0
    sequence = lessons[start_index:] + lessons[:start_index]
    priority_one = [
        lesson for lesson in sequence
        if not progress_rows.get(lesson.id) or not progress_rows[lesson.id].is_completed
    ]

    # Приоритет 2: уроки с ошибками, сначала те, где ошибок больше.
    priority_two = sorted(
        [lesson for lesson in lessons if progress_rows.get(lesson.id)
         and progress_rows[lesson.id].error_count > 0],
        key=lambda lesson: (
            -progress_rows[lesson.id].error_count,
            progress_rows[lesson.id].last_worked_at.timestamp() if progress_rows[lesson.id].last_worked_at else 0,
        ),
    )

    # Приоритет 3: начатые, но ещё не завершённые уроки.
    priority_three = sorted(
        [lesson for lesson in lessons if progress_rows.get(lesson.id)
         and progress_rows[lesson.id].is_started
         and not progress_rows[lesson.id].is_completed],
        key=lambda lesson: progress_rows[lesson.id].last_worked_at or timezone.now(),
    )

    # Приоритет 4: особые блоки возвращаются в план не чаще раза в неделю.
    recommendation_limit = timezone.now() - timedelta(days=7)
    priority_four = [
        lesson for lesson in lessons
        if lesson.special_category in ("culture", "maps")
        and (
            not progress_rows.get(lesson.id)
            or not progress_rows[lesson.id].last_recommended_at
            or progress_rows[lesson.id].last_recommended_at <= recommendation_limit
        )
    ]
    priority_four.sort(key=lambda lesson: (
        progress_rows[lesson.id].last_recommended_at.timestamp()
        if progress_rows.get(lesson.id) and progress_rows[lesson.id].last_recommended_at
        else 0,
        positions[lesson.id],
    ))

    chosen = []
    chosen_ids = set()

    def add_from(items, limit=None):
        for lesson in items:
            if lesson.id in chosen_ids:
                continue
            if limit is not None and len(chosen) >= limit:
                break
            chosen.append(lesson)
            chosen_ids.add(lesson.id)

    # Если есть давно не рекомендованный особый блок, оставляем ему
    # одно место в плане, чтобы он не вытеснялся бесконечно обычными уроками.
    special_lesson = next((lesson for lesson in priority_four), None)
    regular_limit = count - 1 if special_lesson else count
    # Сначала берём ближайший следующий урок, затем работу над ошибками
    # и незавершённые уроки. Остальные последовательные уроки — для заполнения.
    add_from(priority_one[:1], regular_limit)
    add_from(priority_two, regular_limit)
    add_from(priority_three, regular_limit)

    if special_lesson and special_lesson.id not in chosen_ids and len(chosen) < count:
        chosen.append(special_lesson)
        chosen_ids.add(special_lesson.id)

    # Заполняем оставшиеся места последовательными уроками, затем прочими
    # особыми блоками, если они ещё не попали в план.
    add_from(priority_one[1:])
    add_from(priority_two)
    add_from(priority_three)
    add_from(priority_four)

    # Фиксируем рекомендацию для особых уроков, даже если они уже попали
    # в план через один из первых трёх приоритетов.
    recommended_at = timezone.now()
    for lesson in chosen:
        if lesson.special_category in ("culture", "maps"):
            progress, _ = StudentLessonProgress.objects.get_or_create(
                student=student, lesson=lesson
            )
            progress.last_recommended_at = recommended_at
            progress.save(update_fields=["last_recommended_at"])

    return chosen[:count]


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

    # Берём сохранённый выбор из рубрикатора и повторно проверяем,
    # что все ID относятся к предметам текущего ученика.
    selection = request.session.get("rubricator_selection", {})
    selected_subject_ids = _session_ids(selection.get("subject_ids"))
    allowed_subject_ids = {subject.id for subject in student_subjects}
    selected_subject_ids &= allowed_subject_ids

    selected_topic_ids = _session_ids(selection.get("topic_ids"))
    selected_lesson_ids = _session_ids(selection.get("lesson_ids"))
    selected_microtopic_ids = _session_ids(selection.get("microtopic_ids"))

    plan_items_by_subject = {subject.id: [] for subject in student_subjects}

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
        valid_topic_ids = {topic.id for topic in selected_topics}

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
            .order_by("topic__subject_id", "topic__order", "order", "id")
        )
        valid_lesson_ids = {lesson.id for lesson in selected_lessons}

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
            .select_related("lesson", "lesson__topic", "lesson__topic__subject")
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
                "parent": f"{microtopic.lesson.topic.title} / {microtopic.lesson.title}",
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
        "student_mood": request.session.get("student_mood", MOODS[0]),
        "moods": MOODS,
        "student_subjects": student_subjects,
        "streak": 0,
        "tabs": tabs,
        "daily_plan_subjects": daily_plan_subjects,
        "has_rubricator_selection": bool(selection),
        "rubricator_selection_mode": selection.get("mode") or "auto",
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
                messages.success(request, "Выбор сохранён. Он появится в дневном плане кабинета.")

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
    }
    return render(request, "learning/rubricator.html", context)


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
        student, subject, request.POST.get("count", 3), mode=mode
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
