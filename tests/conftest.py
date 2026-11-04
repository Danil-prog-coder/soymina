import itertools
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest
from tortoise import Tortoise, connections
from tortoise.migrations.api.migrate import migrate

from app.config import tortoise_config
from app.models import Department, Task, User, UserRole

MSK = ZoneInfo("Europe/Moscow")


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit("Не задана переменная окружения TEST_DATABASE_URL (см. .env.example)", returncode=2)
    # Тесты удаляют схему целиком, поэтому работаем только с базой, явно помеченной как тестовая.
    if not urlparse(url).path.rstrip("/").endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL должен указывать на базу с суффиксом _test, а не {url}", returncode=2)
    return url


@pytest.fixture(scope="session", autouse=True)
async def database():
    config = tortoise_config(_test_database_url())
    await Tortoise.init(config=config)
    conn = connections.get("default")
    await conn.execute_script("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    # Схему строим той же миграцией, что и в рабочей базе: так проверяются и CHECK-ограничения из неё.
    await migrate(config=config)
    yield
    await Tortoise.close_connections()


@pytest.fixture(autouse=True)
async def clean_tables(database):
    yield
    tables = ", ".join(
        model._meta.db_table for model in Tortoise.apps.get_models_iterable()
    )
    await connections.get("default").execute_script(f"TRUNCATE {tables} RESTART IDENTITY CASCADE;")


_counter = itertools.count(1)


@pytest.fixture
def make_user():
    async def factory(role: UserRole = UserRole.EXECUTOR, department: Department | None = None, **kwargs) -> User:
        n = next(_counter)
        defaults = {
            "login": f"user{n}",
            "password_hash": "x",
            "last_name": "Иванов",
            "first_name": "Иван",
            "position": "инженер",
            "role": role,
            "department": department,
        }
        return await User.create(**(defaults | kwargs))

    return factory


@pytest.fixture
async def manager(make_user) -> User:
    return await make_user(UserRole.MANAGER, last_name="Петров", position="начальник отдела")


@pytest.fixture
async def executor(make_user) -> User:
    return await make_user(UserRole.EXECUTOR)


@pytest.fixture
def make_task(manager, executor):
    async def factory(**kwargs) -> Task:
        n = next(_counter)
        defaults = {
            "number": f"T-{n}",
            "title": "Подготовить отчёт",
            "author": manager,
            "assignee": executor,
            "deadline": datetime.now(MSK) + timedelta(days=3),
        }
        return await Task.create(**(defaults | kwargs))

    return factory
