import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp
import aiosqlite

from parser import parse_profile_json

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("API_TOKEN")

API_BASE = os.getenv("URL_BASE")
DB_FILE = "db.sqlite3"

HEADERS = {
    "Authorization": API_TOKEN,
    "Content-Type": "application/json"
}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ──────────────── FSM ────────────────
class Register(StatesGroup):
    username = State()

# ──────────────── Клавиатура ────────────────
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Зарегистрироваться")],
        [KeyboardButton(text="Профиль")]
    ],
    resize_keyboard=True
)

# ──────────────── DB init ────────────────
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        await db.commit()

# ──────────────── DB utils ────────────────
async def get_user(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT username FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_user(user_id: int, username: str | None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        await db.commit()

# ──────────────── Handlers ────────────────
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id

    user = await get_user(user_id)
    if user is None:
        await set_user(user_id, None)

    await message.answer(
        "Привет 👋\nВыбери действие:",
        reply_markup=keyboard
    )

# ──────────────── Регистрация ────────────────
@dp.message(F.text == "Зарегистрироваться")
async def register(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = await get_user(user_id)

    if username:
        await message.answer("Вы уже зарегистрированы")
        return

    await message.answer("Придумай username:")
    await state.set_state(Register.username)


@dp.message(Register.username)
async def save_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    user_id = message.from_user.id

    await set_user(user_id, username)

    payload = {
        "username": username,
        "traffic_limit": 256,
        "expiration_days": 0
    }

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.post(API_BASE, json=payload) as resp:
            text = await resp.text()

    await message.answer(
        f"✅ Регистрация завершена\n\nОтвет сервера:\n{text}",
        reply_markup=keyboard
    )
    await state.clear()

# ──────────────── Профиль ────────────────
@dp.message(F.text == "Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    username = await get_user(user_id)

    if not username:
        await message.answer("❌ Ты ещё не зарегистрирован")
        return

    url = f"{API_BASE}/{username}/uri"

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url) as resp:
            text = await resp.text()

    profile = parse_profile_json(text)
    lines = [f"👤 <b>{username}</b>:"]
    if profile.ipv4:
        lines.append(f"\n📱 Прямой ключ:\n<code>{profile.ipv4}</code>")
    if profile.normal_sub:
        lines.append(f"\n🔗 Здесь подробная информация:\n{profile.normal_sub}")
    if not profile.ipv4 and not profile.normal_sub:
        lines.append(f"\n{text}")

    await message.answer("\n".join(lines), parse_mode="HTML")

# ──────────────── Run ────────────────
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
