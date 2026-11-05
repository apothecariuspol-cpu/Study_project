
from django.urls import path
from . import views


urlpatterns = [
    path("", views.subject_list, name="subject_list"),
    path("collection-file/<int:file_id>/", views.download_teacher_collection_file, name="download_teacher_collection_file"),

    path(
        "save-mood/",
        views.save_mood,
        name="save_mood",
    ),

    path(
        "cabinet/",
        views.cabinet,
        name="cabinet",
    ),

    path(
        "rubricator/",
        views.rubricator,
        name="rubricator",
    ),
    path(
        "generate-daily-plan/",
        views.generate_daily_plan,
        name="generate_daily_plan",
    ),
    path(
        "start-daily-plan/",
        views.start_daily_plan,
        name="start_daily_plan",
    ),
    path(
        "save-daily-plan-settings/",
        views.save_daily_plan_settings,
        name="save_daily_plan_settings",
    ),

    path(
        "logout/",
        views.logout_student,
        name="logout_student",
    ),

    path(
        "subject/<int:subject_id>/",
        views.topic_list,
        name="topic_list",
    ),

    path(
        "lesson/<int:lesson_id>/",
        views.lesson_detail,
        name="lesson_detail",
    ),
    path(
        "lesson/<int:lesson_id>/complete/",
        views.complete_lesson,
        name="complete_lesson",
    ),
    path(
        "lesson/<int:lesson_id>/record-error/",
        views.record_lesson_error,
        name="record_lesson_error",
    ),
]
