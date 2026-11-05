
from django.urls import path
from . import views

urlpatterns = [
    path("", views.subject_list, name="subject_list"),
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
