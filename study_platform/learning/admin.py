
import hashlib
import hmac

from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Subject, Topic, Lesson, MicroTopic, Student, StudentAccess


class StudentAccessForm(forms.ModelForm):
    code = forms.CharField(
        label="Персональный код",
        required=False,
        strip=True,
        help_text="Укажи код для входа ученика."
    )

    class Meta:
        model = StudentAccess
        fields = ("is_active",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields["code"].required = True

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()

        if not self.instance.pk and not code:
            raise ValidationError("Необходимо указать персональный код.")

        if code:
            lookup = hmac.new(
                settings.SECRET_KEY.encode(),
                code.encode(),
                hashlib.sha256
            ).hexdigest()

            existing = StudentAccess.objects.filter(
                code_lookup=lookup
            ).exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError("Этот код уже назначен другому ученику.")

        return code

    def save(self, commit=True):
        access = super().save(commit=False)

        code = self.cleaned_data.get("code")

        if code:
            access.set_code(code)

        if commit:
            access.save()

        return access


class StudentAccessInline(admin.StackedInline):
    model = StudentAccess
    form = StudentAccessForm
    fields = ("code", "is_active")
    extra = 1
    max_num = 1
    can_delete = False
    verbose_name = "Персональный доступ"
    verbose_name_plural = "Персональный доступ"


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "exam", "is_demo", "access_status")
    list_filter = ("exam", "is_demo", "subjects")
    search_fields = ("name",)
    filter_horizontal = ("subjects",)
    inlines = [StudentAccessInline]

    @admin.display(description="Состояние доступа")
    def access_status(self, obj):
        try:
            return "Включён" if obj.access.is_active else "Заблокирован"
        except StudentAccess.DoesNotExist:
            return "Не назначен"


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("title",)
    search_fields = ("title",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "completion_percent", "order")
    list_filter = ("subject",)
    search_fields = ("title", "description", "hashtags")
    list_editable = ("completion_percent", "order")
    fieldsets = (
        ("Основное", {"fields": ("subject", "title", "description", "period", "hashtags", "order")}),
        ("Показатели", {"fields": ("completion_percent", "theory_percent", "practice_percent", "correct_percent")}),
    )


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "completion_percent", "is_published", "order")
    list_filter = ("is_published", "topic__subject", "topic")
    search_fields = ("title", "description", "content")
    list_editable = ("completion_percent", "is_published", "order")


@admin.register(MicroTopic)
class MicroTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "completion_percent", "is_published", "order")
    list_filter = ("is_published", "lesson__topic__subject", "lesson__topic")
    search_fields = ("title", "lesson__title")
    list_editable = ("completion_percent", "is_published", "order")
    autocomplete_fields = ("lesson",)
