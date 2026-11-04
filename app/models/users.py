from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.migrations.constraints import CheckConstraint
from tortoise.models import Model

from app.models.enums import UserRole, sql_in

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.tasks import Task


class Department(Model):
    """Отдел ИВЦ."""

    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255, unique=True)

    users: fields.ReverseRelation[User]

    class Meta:
        table = "departments"
        constraints = (CheckConstraint(check="btrim(name) <> ''", name="ck_departments_name_not_blank"),)

    def __str__(self) -> str:
        return self.name


class User(Model):
    """Сотрудник. Роль определяет, кто может ставить задачи; получить задачу может любой."""

    id = fields.IntField(primary_key=True)
    login = fields.CharField(max_length=64, unique=True)
    password_hash = fields.CharField(max_length=255)
    last_name = fields.CharField(max_length=100)
    first_name = fields.CharField(max_length=100)
    middle_name = fields.CharField(max_length=100, null=True)
    position = fields.CharField(max_length=255)
    department: fields.ForeignKeyNullableRelation[Department] = fields.ForeignKeyField(
        "models.Department", related_name="users", null=True, on_delete=fields.RESTRICT
    )
    role = fields.CharEnumField(UserRole, max_length=16)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    authored_tasks: fields.ReverseRelation[Task]
    assigned_tasks: fields.ReverseRelation[Task]
    audit_records: fields.ReverseRelation[AuditLog]

    class Meta:
        table = "users"
        constraints = (
            CheckConstraint(check=sql_in("role", UserRole), name="ck_users_role"),
            CheckConstraint(check="btrim(login) <> ''", name="ck_users_login_not_blank"),
        )

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    def __str__(self) -> str:
        return self.full_name


class Recipient(Model):
    """Адресат документа: по ГОСТ Р 7.0.97-2016 реквизит из нескольких частей."""

    id = fields.IntField(primary_key=True)
    organization = fields.CharField(max_length=255)
    department = fields.CharField(max_length=255, null=True)
    position = fields.CharField(max_length=255, null=True)
    full_name = fields.CharField(max_length=255, null=True)
    address = fields.TextField(null=True)

    tasks: fields.ReverseRelation[Task]

    class Meta:
        table = "recipients"
        constraints = (
            CheckConstraint(check="btrim(organization) <> ''", name="ck_recipients_organization_not_blank"),
        )

    def __str__(self) -> str:
        return self.organization
