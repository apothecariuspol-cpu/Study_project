
from django.urls import path
from . import views


urlpatterns = [
    path("", views.subject_list, name="subject_list"),

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
]
