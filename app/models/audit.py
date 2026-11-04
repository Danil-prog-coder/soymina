from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.models import Model

if TYPE_CHECKING:
    from app.models.users import User


class AuditLog(Model):
    """Журнал действий пользователей (152-ФЗ: учёт доступа к персональным данным).

    Только добавление записей. user пуст для действий самой системы.
    """

    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="audit_records", null=True, on_delete=fields.RESTRICT
    )
    action = fields.CharField(max_length=64)
    entity = fields.CharField(max_length=64)
    entity_id = fields.IntField(null=True)
    ip_address = fields.CharField(max_length=45, null=True)
    details = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "audit_log"
        indexes = (("entity", "entity_id"), ("user_id", "created_at"), ("created_at",))
