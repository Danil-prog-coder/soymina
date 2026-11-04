import os

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name} (см. .env.example)")
    return value


def tortoise_config(database_url: str) -> dict:
    return {
        "connections": {"default": database_url},
        "apps": {
            "models": {
                "models": ["app.models"],
                "migrations": "app.migrations",
                "default_connection": "default",
            }
        },
        "use_tz": True,
        "timezone": "Europe/Moscow",
    }


DATABASE_URL = _require_env("DATABASE_URL")

TORTOISE_ORM = tortoise_config(DATABASE_URL)
