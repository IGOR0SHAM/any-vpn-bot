"""
Модуль работы с БД пользователей.
Поле id — внутренний идентификатор записи в БД, по нему можно обращаться к пользователю.
"""
import aiosqlite
from typing import NamedTuple

DB_FILE = "db.sqlite3"


class UserRow(NamedTuple):
    """Запись пользователя: id в БД, Telegram user_id, username в API, first_name, last_name."""
    id: int
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


async def init_db() -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT
            )
        """)
        await db.commit()

        # Миграция: добавить first_name, last_name если их нет (старая схема)
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        for col in ("first_name", "last_name"):
            if col not in columns:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                    await db.commit()
                except Exception:
                    pass

        # Миграция: если таблица без колонки id — пересоздать с id
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        if "id" not in columns:
            await db.execute("""
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT
                )
            """)
            await db.execute("""
                INSERT INTO users_new (user_id, username, first_name, last_name)
                SELECT user_id, username, first_name, last_name FROM users
            """)
            await db.execute("DROP TABLE users")
            await db.execute("ALTER TABLE users_new RENAME TO users")
            await db.commit()


async def get_user(user_id: int) -> str | None:
    """Возвращает username в API по Telegram user_id или None."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT username FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_user_by_id(pk: int) -> UserRow | None:
    """Возвращает запись пользователя по внутреннему id в БД или None."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, user_id, username, first_name, last_name FROM users WHERE id = ?",
            (pk,)
        ) as cursor:
            row = await cursor.fetchone()
            return UserRow(*row) if row else None


async def set_user(
    user_id: int,
    username: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                first_name = COALESCE(excluded.first_name, first_name),
                last_name = COALESCE(excluded.last_name, last_name)
        """, (user_id, username, first_name or None, last_name or None))
        await db.commit()


async def get_all_users() -> list[UserRow]:
    """Возвращает всех пользователей (id, user_id, username, first_name, last_name)."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, user_id, username, first_name, last_name FROM users ORDER BY id"
        ) as cursor:
            return [UserRow(*row) for row in await cursor.fetchall()]
