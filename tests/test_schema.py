"""Связи между таблицами и ограничения, которые держит сама PostgreSQL."""

from datetime import date, datetime, timedelta

import pytest
from tortoise import connections
from tortoise.exceptions import IntegrityError

from app.models import (
    AuditLog,
    DeadlineChange,
    Department,
    Document,
    DocumentFormat,
    DocumentSource,
    DocumentTemplate,
    Recipient,
    ReviewDecision,
    Submission,
    Task,
    TaskStatus,
    TaskStatusHistory,
    User,
    UserRole,
)
from tests.conftest import MSK


async def make_document(task: Task, author: User, **kwargs) -> Document:
    defaults = {
        "task": task,
        "source": DocumentSource.UPLOADED,
        "file_name": "отчёт.docx",
        "file_path": "storage/1.docx",
        "format": DocumentFormat.DOCX,
        "size": 1024,
        "sha256": "0" * 64,
        "created_by": author,
    }
    return await Document.create(**(defaults | kwargs))


# --- Связи ---------------------------------------------------------------


async def test_full_task_lifecycle_relations(make_user, manager, make_task):
    department = await Department.create(name="Отдел сопровождения АСУ")
    executor = await make_user(UserRole.EXECUTOR, department=department)
    template = await DocumentTemplate.create(code="memo", name="Служебная записка", file_path="templates/memo.docx")
    recipient = await Recipient.create(organization="Северная железная дорога", position="Начальник")

    task = await make_task(
        assignee=executor,
        document_required=True,
        document_format=DocumentFormat.DOCX,
        template=template,
        recipient=recipient,
    )
    await TaskStatusHistory.create(task=task, from_status=None, to_status=TaskStatus.NEW, changed_by=manager)
    await DeadlineChange.create(
        task=task, old_deadline=task.deadline, new_deadline=task.deadline + timedelta(days=2), changed_by=manager
    )
    document = await make_document(task, executor, source=DocumentSource.GENERATED, template=template)
    submission = await Submission.create(task=task, submitted_by=executor, document=document)

    task = await Task.get(id=task.id).prefetch_related(
        "author", "assignee", "template", "recipient", "status_history", "deadline_changes", "submissions", "documents"
    )
    assert task.author.id == manager.id
    assert task.assignee.id == executor.id
    assert task.template.code == "memo"
    assert task.recipient.organization == "Северная железная дорога"
    assert [h.to_status for h in task.status_history] == [TaskStatus.NEW]
    assert len(task.deadline_changes) == 1
    assert [s.id for s in task.submissions] == [submission.id]
    assert [d.id for d in task.documents] == [document.id]

    await department.fetch_related("users")
    assert [u.id for u in department.users] == [executor.id]
    await executor.fetch_related("assigned_tasks")
    assert [t.id for t in executor.assigned_tasks] == [task.id]
    await manager.fetch_related("authored_tasks")
    assert [t.id for t in manager.authored_tasks] == [task.id]
    await document.fetch_related("submissions")
    assert [s.id for s in document.submissions] == [submission.id]


async def test_optional_relations_may_be_empty(make_task):
    task = await make_task()
    await task.fetch_related("template", "recipient", "closed_by")
    assert task.template is None
    assert task.recipient is None
    assert task.closed_by is None
    assert task.status == TaskStatus.NEW


async def test_audit_log_without_user_and_json_details(executor):
    await AuditLog.create(user=None, action="mark_overdue", entity="task", entity_id=1, details={"дней": 2})
    await AuditLog.create(user=executor, action="login", entity="user", entity_id=executor.id)
    system_record = await AuditLog.get(action="mark_overdue")
    assert system_record.user_id is None
    assert system_record.details == {"дней": 2}
    assert (await AuditLog.get(action="login")).details == {}


# --- Удаление с RESTRICT: журналы не теряют записи --------------------------


async def test_cannot_delete_user_with_tasks(manager, make_task):
    await make_task()
    with pytest.raises(IntegrityError, match="foreign key constraint"):
        await manager.delete()


async def test_cannot_delete_task_with_history(manager, make_task):
    task = await make_task()
    await TaskStatusHistory.create(task=task, to_status=TaskStatus.NEW, changed_by=manager)
    with pytest.raises(IntegrityError, match="foreign key constraint"):
        await task.delete()


async def test_cannot_delete_department_with_users(make_user):
    department = await Department.create(name="Отдел")
    await make_user(department=department)
    with pytest.raises(IntegrityError, match="foreign key constraint"):
        await department.delete()


async def test_cannot_delete_template_used_by_document(make_task, executor):
    template = await DocumentTemplate.create(code="memo", name="Служебная записка", file_path="t.docx")
    task = await make_task()
    await make_document(task, executor, source=DocumentSource.GENERATED, template=template)
    with pytest.raises(IntegrityError, match="foreign key constraint"):
        await template.delete()


# --- Задача ----------------------------------------------------------------


async def test_task_with_document_requires_format(make_task):
    with pytest.raises(IntegrityError, match="ck_tasks_document_format_required"):
        await make_task(document_required=True, document_format=None)


async def test_only_author_can_close_task(make_task, executor):
    task = await make_task()
    task.status = TaskStatus.DONE
    task.closed_by = executor
    task.closed_at = datetime.now(MSK)
    with pytest.raises(IntegrityError, match="ck_tasks_closed_by_author"):
        await task.save()


async def test_author_closes_task(make_task, manager):
    task = await make_task()
    task.status = TaskStatus.DONE
    task.closed_by = manager
    task.closed_at = datetime.now(MSK)
    await task.save()
    assert (await Task.get(id=task.id)).status == TaskStatus.DONE


@pytest.mark.parametrize("closed_by_set, closed_at_set", [(False, False), (True, False), (False, True)])
async def test_done_status_requires_closing_fields(make_task, manager, closed_by_set, closed_at_set):
    task = await make_task()
    task.status = TaskStatus.DONE
    task.closed_by = manager if closed_by_set else None
    task.closed_at = datetime.now(MSK) if closed_at_set else None
    with pytest.raises(IntegrityError, match="ck_tasks_done_is_closed"):
        await task.save()


async def test_open_task_cannot_have_closed_by(make_task, manager):
    task = await make_task()
    task.closed_by = manager
    task.closed_at = datetime.now(MSK)
    with pytest.raises(IntegrityError, match="ck_tasks_done_is_closed"):
        await task.save()


async def test_task_status_outside_enum_rejected_by_database(make_task):
    task = await make_task()
    with pytest.raises(IntegrityError, match="ck_tasks_status"):
        await connections.get("default").execute_query(
            "UPDATE tasks SET status = 'archived' WHERE id = $1", [task.id]
        )


@pytest.mark.parametrize("title", ["", "   "])
async def test_task_title_not_blank(make_task, title):
    with pytest.raises(IntegrityError, match="ck_tasks_title_not_blank"):
        await make_task(title=title)


async def test_task_number_unique(make_task):
    await make_task(number="T-1")
    with pytest.raises(IntegrityError, match="tasks_number_key"):
        await make_task(number="T-1")


# --- Сроки -----------------------------------------------------------------


@pytest.mark.parametrize("shift", [timedelta(0), timedelta(hours=-1)])
async def test_deadline_change_must_extend(make_task, manager, shift):
    task = await make_task()
    with pytest.raises(IntegrityError, match="ck_deadline_changes_extends"):
        await DeadlineChange.create(
            task=task, old_deadline=task.deadline, new_deadline=task.deadline + shift, changed_by=manager
        )


# --- Сдача и проверка ------------------------------------------------------


async def test_only_one_pending_submission_per_task(make_task, executor, manager):
    task = await make_task()
    first = await Submission.create(task=task, submitted_by=executor)
    with pytest.raises(IntegrityError, match="uq_submissions_one_pending_per_task"):
        await Submission.create(task=task, submitted_by=executor)

    first.decision = ReviewDecision.REJECTED
    first.decided_by = manager
    first.decided_at = datetime.now(MSK)
    first.decision_comment = "Нет подписи"
    await first.save()

    await Submission.create(task=task, submitted_by=executor)
    assert await Submission.filter(task=task).count() == 2


async def test_pending_submissions_of_different_tasks_allowed(make_task, executor):
    await Submission.create(task=await make_task(), submitted_by=executor)
    await Submission.create(task=await make_task(), submitted_by=executor)
    assert await Submission.all().count() == 2


@pytest.mark.parametrize("comment", ["", "  "])
async def test_rejection_requires_reason(make_task, executor, manager, comment):
    task = await make_task()
    with pytest.raises(IntegrityError, match="ck_submissions_rejection_has_reason"):
        await Submission.create(
            task=task,
            submitted_by=executor,
            decision=ReviewDecision.REJECTED,
            decided_by=manager,
            decided_at=datetime.now(MSK),
            decision_comment=comment,
        )


async def test_acceptance_without_comment_allowed(make_task, executor, manager):
    task = await make_task()
    await Submission.create(
        task=task, submitted_by=executor, decision=ReviewDecision.ACCEPTED, decided_by=manager, decided_at=datetime.now(MSK)
    )


async def test_decision_requires_reviewer_and_time(make_task, executor):
    task = await make_task()
    with pytest.raises(IntegrityError, match="ck_submissions_decision_complete"):
        await Submission.create(task=task, submitted_by=executor, decision=ReviewDecision.ACCEPTED)


# --- Документы -------------------------------------------------------------


async def test_generated_document_requires_template(make_task, executor):
    task = await make_task()
    with pytest.raises(IntegrityError, match="ck_documents_generated_has_template"):
        await make_document(task, executor, source=DocumentSource.GENERATED, template=None)


async def test_uploaded_document_without_template_allowed(make_task, executor):
    document = await make_document(await make_task(), executor)
    assert document.template_id is None


@pytest.mark.parametrize("reg_number, reg_date", [("ИВЦ-1", None), (None, date(2026, 11, 5))])
async def test_registration_needs_number_and_date(make_task, executor, reg_number, reg_date):
    with pytest.raises(IntegrityError, match="ck_documents_registration_complete"):
        await make_document(await make_task(), executor, reg_number=reg_number, reg_date=reg_date)


async def test_registration_number_unique(make_task, executor):
    task = await make_task()
    await make_document(task, executor, reg_number="ИВЦ-1", reg_date=date(2026, 11, 5))
    with pytest.raises(IntegrityError, match="documents_reg_number_key"):
        await make_document(task, executor, reg_number="ИВЦ-1", reg_date=date(2026, 11, 5))


async def test_unregistered_documents_do_not_clash(make_task, executor):
    task = await make_task()
    await make_document(task, executor)
    await make_document(task, executor)
    assert await Document.filter(reg_number__isnull=True).count() == 2


async def test_document_size_non_negative(make_task, executor):
    with pytest.raises(IntegrityError, match="ck_documents_size_non_negative"):
        await make_document(await make_task(), executor, size=-1)


async def test_template_code_version_unique():
    await DocumentTemplate.create(code="memo", name="Служебная записка", file_path="a.docx", version=1)
    await DocumentTemplate.create(code="memo", name="Служебная записка", file_path="b.docx", version=2)
    with pytest.raises(IntegrityError, match="uid_document_te_code"):
        await DocumentTemplate.create(code="memo", name="Служебная записка", file_path="c.docx", version=2)


# --- Пользователи ----------------------------------------------------------


async def test_login_unique(make_user):
    await make_user(login="ivanov")
    with pytest.raises(IntegrityError, match="users_login_key"):
        await make_user(login="ivanov")


async def test_user_role_outside_enum_rejected_by_database(executor):
    with pytest.raises(IntegrityError, match="ck_users_role"):
        await connections.get("default").execute_query(
            "UPDATE users SET role = 'root' WHERE id = $1", [executor.id]
        )


async def test_full_name(make_user):
    with_middle = await make_user(last_name="Сидоров", first_name="Пётр", middle_name="Ильич")
    without_middle = await make_user(last_name="Сидоров", first_name="Пётр", middle_name=None)
    assert with_middle.full_name == "Сидоров Пётр Ильич"
    assert without_middle.full_name == "Сидоров Пётр"
