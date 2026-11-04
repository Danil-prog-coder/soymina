from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.migrations.constraints import CheckConstraint, UniqueConstraint
from tortoise.models import Model

from app.models.enums import DocumentFormat, ReviewDecision, TaskStatus, sql_in

if TYPE_CHECKING:
    from app.models.documents import Document, DocumentTemplate
    from app.models.users import Recipient, User


class Task(Model):
    """Карточка задачи (блок A1).

    Просрочка не хранится, а вычисляется: deadline < now() и статус не done.
    Сохранённый флаг устаревал бы при каждом продлении срока.
    """

    id = fields.IntField(primary_key=True)
    number = fields.CharField(max_length=32, unique=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(default="")
    author: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="authored_tasks", on_delete=fields.RESTRICT
    )
    assignee: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="assigned_tasks", on_delete=fields.RESTRICT
    )
    status = fields.CharEnumField(TaskStatus, max_length=16, default=TaskStatus.NEW)
    deadline = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    accepted_at = fields.DatetimeField(null=True)
    closed_at = fields.DatetimeField(null=True)
    closed_by: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="closed_tasks", null=True, on_delete=fields.RESTRICT
    )
    document_required = fields.BooleanField(default=False)
    template: fields.ForeignKeyNullableRelation[DocumentTemplate] = fields.ForeignKeyField(
        "models.DocumentTemplate", related_name="tasks", null=True, on_delete=fields.RESTRICT
    )
    document_format = fields.CharEnumField(DocumentFormat, max_length=8, null=True)
    recipient: fields.ForeignKeyNullableRelation[Recipient] = fields.ForeignKeyField(
        "models.Recipient", related_name="tasks", null=True, on_delete=fields.RESTRICT
    )
    board_order = fields.IntField(default=0)

    status_history: fields.ReverseRelation[TaskStatusHistory]
    deadline_changes: fields.ReverseRelation[DeadlineChange]
    submissions: fields.ReverseRelation[Submission]
    documents: fields.ReverseRelation[Document]

    class Meta:
        table = "tasks"
        # Канбан исполнителя: его задачи по колонкам; контроль сроков: открытые задачи по дедлайну.
        indexes = (("assignee_id", "status"), ("status", "deadline"))
        constraints = (
            CheckConstraint(check=sql_in("status", TaskStatus), name="ck_tasks_status"),
            CheckConstraint(
                check=f"document_format IS NULL OR {sql_in('document_format', DocumentFormat)}",
                name="ck_tasks_document_format",
            ),
            CheckConstraint(check="btrim(title) <> ''", name="ck_tasks_title_not_blank"),
            CheckConstraint(
                check="NOT document_required OR document_format IS NOT NULL",
                name="ck_tasks_document_format_required",
            ),
            # Закрыть задачу может только тот, кто её поставил.
            CheckConstraint(
                check="closed_by_id IS NULL OR closed_by_id = author_id",
                name="ck_tasks_closed_by_author",
            ),
            CheckConstraint(
                check="(status = 'done') = (closed_by_id IS NOT NULL AND closed_at IS NOT NULL)",
                name="ck_tasks_done_is_closed",
            ),
        )

    def __str__(self) -> str:
        return f"{self.number} {self.title}"


class TaskStatusHistory(Model):
    """Каждая смена статуса задачи (блок A5). from_status пуст для создания задачи."""

    id = fields.IntField(primary_key=True)
    task: fields.ForeignKeyRelation[Task] = fields.ForeignKeyField(
        "models.Task", related_name="status_history", on_delete=fields.RESTRICT
    )
    from_status = fields.CharEnumField(TaskStatus, max_length=16, null=True)
    to_status = fields.CharEnumField(TaskStatus, max_length=16)
    changed_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="status_changes", on_delete=fields.RESTRICT
    )
    changed_at = fields.DatetimeField(auto_now_add=True)
    comment = fields.TextField(default="")

    class Meta:
        table = "task_status_history"
        indexes = (("task_id", "changed_at"),)
        constraints = (
            CheckConstraint(
                check=f"from_status IS NULL OR {sql_in('from_status', TaskStatus)}",
                name="ck_task_status_history_from_status",
            ),
            CheckConstraint(check=sql_in("to_status", TaskStatus), name="ck_task_status_history_to_status"),
        )


class DeadlineChange(Model):
    """Продление срока руководителем (стрелка «Новый срок исполнения» из A4)."""

    id = fields.IntField(primary_key=True)
    task: fields.ForeignKeyRelation[Task] = fields.ForeignKeyField(
        "models.Task", related_name="deadline_changes", on_delete=fields.RESTRICT
    )
    old_deadline = fields.DatetimeField()
    new_deadline = fields.DatetimeField()
    changed_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="deadline_changes", on_delete=fields.RESTRICT
    )
    changed_at = fields.DatetimeField(auto_now_add=True)
    reason = fields.TextField(default="")

    class Meta:
        table = "deadline_changes"
        constraints = (
            CheckConstraint(check="new_deadline > old_deadline", name="ck_deadline_changes_extends"),
        )


class Submission(Model):
    """Попытка сдачи задачи: «Решение на проверку» (A3 → A4) и «Итог проверки» (A4 → A5)."""

    id = fields.IntField(primary_key=True)
    task: fields.ForeignKeyRelation[Task] = fields.ForeignKeyField(
        "models.Task", related_name="submissions", on_delete=fields.RESTRICT
    )
    submitted_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="submissions", on_delete=fields.RESTRICT
    )
    submitted_at = fields.DatetimeField(auto_now_add=True)
    comment = fields.TextField(default="")
    document: fields.ForeignKeyNullableRelation[Document] = fields.ForeignKeyField(
        "models.Document", related_name="submissions", null=True, on_delete=fields.RESTRICT
    )
    decision = fields.CharEnumField(ReviewDecision, max_length=16, null=True)
    decided_by: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="reviewed_submissions", null=True, on_delete=fields.RESTRICT
    )
    decided_at = fields.DatetimeField(null=True)
    decision_comment = fields.TextField(default="")

    class Meta:
        table = "submissions"
        constraints = (
            CheckConstraint(
                check=f"decision IS NULL OR {sql_in('decision', ReviewDecision)}",
                name="ck_submissions_decision",
            ),
            CheckConstraint(
                check="(decision IS NULL) = (decided_by_id IS NULL) AND (decision IS NULL) = (decided_at IS NULL)",
                name="ck_submissions_decision_complete",
            ),
            # Отклонение без причины исполнителю ничего не даёт.
            CheckConstraint(
                check="decision IS DISTINCT FROM 'rejected' OR btrim(decision_comment) <> ''",
                name="ck_submissions_rejection_has_reason",
            ),
            # У задачи не может быть двух непроверенных сдач одновременно (защита от двойной отправки).
            UniqueConstraint(
                fields=("task_id",),
                name="uq_submissions_one_pending_per_task",
                condition="decision IS NULL",
            ),
        )
