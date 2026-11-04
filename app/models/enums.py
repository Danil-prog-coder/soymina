from enum import StrEnum


class UserRole(StrEnum):
    MANAGER = "manager"
    EXECUTOR = "executor"
    ADMIN = "admin"


class TaskStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class DocumentFormat(StrEnum):
    DOCX = "docx"
    PDF = "pdf"


class DocumentSource(StrEnum):
    GENERATED = "generated"
    UPLOADED = "uploaded"


class ReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def sql_in(column: str, enum: type[StrEnum]) -> str:
    """SQL-условие для CHECK: значение колонки входит в перечисление."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
