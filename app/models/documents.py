from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.migrations.constraints import CheckConstraint
from tortoise.models import Model

from app.models.enums import DocumentFormat, DocumentSource, sql_in

if TYPE_CHECKING:
    from app.models.tasks import Submission, Task
    from app.models.users import User


class DocumentTemplate(Model):
    """Шаблон документа (.docx с метками для подстановки данных из карточки задачи)."""

    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=64)
    name = fields.CharField(max_length=255)
    file_path = fields.CharField(max_length=500)
    version = fields.IntField(default=1)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    tasks: fields.ReverseRelation[Task]
    documents: fields.ReverseRelation[Document]

    class Meta:
        table = "document_templates"
        unique_together = (("code", "version"),)
        constraints = (CheckConstraint(check="version >= 1", name="ck_document_templates_version_positive"),)

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"


class Document(Model):
    """Файл документа по задаче: сгенерированный черновик или приложенный вручную.

    Журнал документов — это выборка записей с заполненным reg_number.
    """

    id = fields.IntField(primary_key=True)
    task: fields.ForeignKeyRelation[Task] = fields.ForeignKeyField(
        "models.Task", related_name="documents", on_delete=fields.RESTRICT
    )
    template: fields.ForeignKeyNullableRelation[DocumentTemplate] = fields.ForeignKeyField(
        "models.DocumentTemplate", related_name="documents", null=True, on_delete=fields.RESTRICT
    )
    source = fields.CharEnumField(DocumentSource, max_length=16)
    file_name = fields.CharField(max_length=255)
    file_path = fields.CharField(max_length=500)
    format = fields.CharEnumField(DocumentFormat, max_length=8)
    size = fields.BigIntField()
    sha256 = fields.CharField(max_length=64)
    created_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="created_documents", on_delete=fields.RESTRICT
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    reg_number = fields.CharField(max_length=64, null=True, unique=True)
    reg_date = fields.DateField(null=True)

    submissions: fields.ReverseRelation[Submission]

    class Meta:
        table = "documents"
        constraints = (
            CheckConstraint(check=sql_in("source", DocumentSource), name="ck_documents_source"),
            CheckConstraint(check=sql_in("format", DocumentFormat), name="ck_documents_format"),
            CheckConstraint(check="size >= 0", name="ck_documents_size_non_negative"),
            # Черновик без шаблона сгенерировать нельзя; ручной файл может быть без шаблона.
            CheckConstraint(
                check="source = 'uploaded' OR template_id IS NOT NULL",
                name="ck_documents_generated_has_template",
            ),
            CheckConstraint(
                check="(reg_number IS NULL) = (reg_date IS NULL)",
                name="ck_documents_registration_complete",
            ),
        )

    def __str__(self) -> str:
        return self.file_name
