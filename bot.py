import os
import asyncio
import json
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp

from parser import parse_profile_json
from database import init_db, get_user, set_user, get_all_users

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_ID", "").split(",") if x.strip()]

API_BASE = os.getenv("URL_BASE")

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

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Зарегистрироваться")],
        [KeyboardButton(text="Профиль")],
        [KeyboardButton(text="Список"), KeyboardButton(text="БД")]
    ],
    resize_keyboard=True
)


def get_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    return admin_keyboard if user_id in ADMIN_IDS else keyboard

# ──────────────── Handlers ────────────────
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id

    u = message.from_user
    user = await get_user(user_id)
    if user is None:
        await set_user(user_id, None, u.first_name, u.last_name)
    else:
        await set_user(user_id, user, u.first_name, u.last_name)

    await message.answer(
        "Привет 👋\nВыбери действие:",
        reply_markup=get_keyboard(user_id)
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

    u = message.from_user
    await set_user(user_id, username, u.first_name, u.last_name)

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
        reply_markup=get_keyboard(user_id)
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

# ──────────────── Админ: Список пользователей ────────────────
def parse_users_from_api(data) -> list[str]:
    """Из ответа API извлекаем список username."""
    usernames = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "username" in item:
                usernames.append(str(item["username"]))
            elif isinstance(item, str):
                usernames.append(item)
    elif isinstance(data, dict):
        if "users" in data and isinstance(data["users"], list):
            for item in data["users"]:
                if isinstance(item, dict) and "username" in item:
                    usernames.append(str(item["username"]))
                elif isinstance(item, str):
                    usernames.append(item)
        elif "username" in data:
            usernames.append(str(data["username"]))
    return usernames


@dp.message(F.text == "Список")
async def admin_list(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(API_BASE) as resp:
            text = await resp.text()
    try:
        data = json.loads(text)
    except Exception:
        await message.answer(f"Не удалось разобрать ответ API.\n\n{text[:2000]}")
        return
    usernames = parse_users_from_api(data)
    if not usernames:
        await message.answer("Список пуст или формат ответа не распознан.")
        return
    lines = ["📋 <b>Пользователи:</b>\n"] + [f"• {u}" for u in sorted(usernames)]
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n… (обрезано)"
    await message.answer(msg, parse_mode="HTML")


@dp.message(F.text == "БД")
async def admin_db_list(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    rows = await get_all_users()
    if not rows:
        await message.answer("В БД пока никого нет.")
        return
    lines = ["📋 <b>Пользователи (БД):</b>\nФормат: id — user_id — username в API — first_name last_name\n"]
    for row in rows:
        name = " ".join(filter(None, (row.first_name or "", row.last_name or ""))).strip() or "—"
        api_user = row.username or "—"
        lines.append(f"<code>{row.id}</code> — <code>{row.user_id}</code> — {api_user} — {name}")
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n… (обрезано)"
    await message.answer(msg, parse_mode="HTML")

# ──────────────── Run ────────────────
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
