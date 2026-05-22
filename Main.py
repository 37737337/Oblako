# =========================================================
# FILESHIELD CLOUD
# ULTRA STABLE VERSION
# =========================================================

import asyncio
import sqlite3
import random
import os

from dotenv import load_dotenv
from cryptography.fernet import Fernet

from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)

# =========================================================
# ENV
# =========================================================

load_dotenv()

TOKEN = os.getenv("TOKEN")

# =========================================================
# BOT
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()

# =========================================================
# CONFIG
# =========================================================

FILE_LIFETIME = 3600
TWOFA_LIFETIME = 30
MAX_ATTEMPTS = 3

# =========================================================
# ENCRYPTION
# =========================================================

KEY = Fernet.generate_key()
cipher = Fernet(KEY)

def encrypt_text(text):

    return cipher.encrypt(
        text.encode()
    ).decode()

def decrypt_text(text):

    return cipher.decrypt(
        text.encode()
    ).decode()

# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(
    "cloud.db"
)

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    current_folder TEXT DEFAULT 'root'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    folder TEXT,
    file_id TEXT,
    file_name TEXT,
    code TEXT,
    favorite INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    created_at TEXT,
    expires TEXT
)
""")

db.commit()

# =========================================================
# STATES
# =========================================================

upload_users = set()
folder_users = set()
search_users = set()

waiting_2fa = {}
attempts = {}

# =========================================================
# MENU
# =========================================================

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="☁️ Облако"
            )
        ],
        [
            KeyboardButton(
                text="📤 Загрузить"
            ),
            KeyboardButton(
                text="➕ Папка"
            )
        ],
        [
            KeyboardButton(
                text="🔎 Поиск"
            ),
            KeyboardButton(
                text="⭐ Избранное"
            )
        ]
    ],
    resize_keyboard=True
)

# =========================================================
# FUNCTIONS
# =========================================================

def create_code():

    return ''.join(
        random.choice(
            "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        )
        for _ in range(8)
    )

def get_current_folder(user_id):

    cursor.execute(
        """
        SELECT current_folder
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )

    data = cursor.fetchone()

    if not data:

        cursor.execute(
            """
            INSERT INTO users
            (
                user_id,
                current_folder
            )
            VALUES (?, ?)
            """,
            (
                user_id,
                "root"
            )
        )

        db.commit()

        return "root"

    return data[0]

def set_current_folder(
    user_id,
    folder
):

    cursor.execute(
        """
        INSERT OR REPLACE INTO users
        (
            user_id,
            current_folder
        )
        VALUES (?, ?)
        """,
        (
            user_id,
            folder
        )
    )

    db.commit()

# =========================================================
# SHOW CLOUD
# =========================================================

async def show_cloud(target, user_id):

    current_folder = get_current_folder(
        user_id
    )

    buttons = []

    # =====================================================
    # BACK
    # =====================================================

    if current_folder != "root":

        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_root"
            )
        ])

    # =====================================================
    # FOLDERS
    # =====================================================

    if current_folder == "root":

        cursor.execute(
            """
            SELECT name
            FROM folders
            WHERE user_id=?
            """,
            (user_id,)
        )

        folders = cursor.fetchall()

        for folder in folders:

            buttons.append([
                InlineKeyboardButton(
                    text=f"📂 {folder[0]}",
                    callback_data=f"open:{folder[0]}"
                )
            ])

    # =====================================================
    # FILES
    # =====================================================

    cursor.execute(
        """
        SELECT file_name,
               code
        FROM files
        WHERE owner_id=?
        AND folder=?
        """,
        (
            user_id,
            current_folder
        )
    )

    files = cursor.fetchall()

    for file_name, code in files:

        real_name = decrypt_text(
            file_name
        )

        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {real_name}",
                callback_data=f"file:{code}"
            )
        ])

    # =====================================================
    # EMPTY
    # =====================================================

    if not buttons:

        buttons.append([
            InlineKeyboardButton(
                text="📭 Пусто",
                callback_data="empty"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    text = f"""
☁️ Folder:
{current_folder}
"""

    try:

        if isinstance(target, Message):

            await target.answer(
                text,
                reply_markup=kb
            )

        else:

            await target.message.edit_text(
                text,
                reply_markup=kb
            )

    except:

        pass

# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):

    args = message.text.split()

    # =====================================================
    # SHARE LINK
    # =====================================================

    if len(args) > 1:

        code = args[1]

        cursor.execute(
            """
            SELECT owner_id,
                   file_id,
                   file_name
            FROM files
            WHERE code=?
            """,
            (code,)
        )

        data = cursor.fetchone()

        if not data:

            await message.answer(
                "❌ Файл не найден"
            )

            return

        owner_id, file_id, file_name = data

        real_name = decrypt_text(
            file_name
        )

        twofa = create_code()

        waiting_2fa[
            message.from_user.id
        ] = {
            "code": code,
            "2fa": twofa,
            "expires": (
                datetime.now() +
                timedelta(
                    seconds=TWOFA_LIFETIME
                )
            )
        }

        attempts[
            message.from_user.id
        ] = 0

        await bot.send_message(
            owner_id,
            f"""
⚠️ Кто-то хочет скачать файл

📄 {real_name}

🛡 CODE:
{twofa}

⏳ 30 секунд
"""
        )

        await message.answer(
            "🛡 Введите 2FA CODE:"
        )

        return

    await message.answer(
        """
🔥 FILESHIELD CLOUD

☁️ Облако
📂 Папки
📤 Загрузка
🔗 Share Links
🛡 2FA
""",
        reply_markup=main_kb
    )

# =========================================================
# CLOUD
# =========================================================

@dp.message(
    F.text == "☁️ Облако"
)
async def cloud(message: Message):

    await show_cloud(
        message,
        message.from_user.id
    )

# =========================================================
# OPEN FOLDER
# =========================================================

@dp.callback_query(
    F.data.startswith("open:")
)
async def open_folder(call: CallbackQuery):

    folder = call.data.split(":")[1]

    set_current_folder(
        call.from_user.id,
        folder
    )

    await call.answer()

    await show_cloud(
        call,
        call.from_user.id
    )

# =========================================================
# BACK
# =========================================================

@dp.callback_query(
    F.data == "back_root"
)
async def back_root(call: CallbackQuery):

    set_current_folder(
        call.from_user.id,
        "root"
    )

    await call.answer()

    await show_cloud(
        call,
        call.from_user.id
    )

# =========================================================
# EMPTY
# =========================================================

@dp.callback_query(
    F.data == "empty"
)
async def empty(call: CallbackQuery):

    await call.answer(
        "📭 Пусто"
    )

# =========================================================
# CREATE FOLDER
# =========================================================

@dp.message(
    F.text == "➕ Папка"
)
async def create_folder(message: Message):

    folder_users.add(
        message.from_user.id
    )

    await message.answer(
        "📂 Введите название папки:"
    )

# =========================================================
# SEARCH
# =========================================================

@dp.message(
    F.text == "🔎 Поиск"
)
async def search(message: Message):

    search_users.add(
        message.from_user.id
    )

    await message.answer(
        "🔎 Введите название файла:"
    )

# =========================================================
# UPLOAD
# =========================================================

@dp.message(
    F.text == "📤 Загрузить"
)
async def upload(message: Message):

    upload_users.add(
        message.from_user.id
    )

    folder = get_current_folder(
        message.from_user.id
    )

    await message.answer(
        f"""
📤 Отправьте файл

📂 Folder:
{folder}
"""
    )

# =========================================================
# FILE UPLOAD
# =========================================================

@dp.message(F.document)
async def upload_file(message: Message):

    user_id = message.from_user.id

    if user_id not in upload_users:
        return

    upload_users.remove(user_id)

    folder = get_current_folder(
        user_id
    )

    code = create_code()

    encrypted_name = encrypt_text(
        message.document.file_name
    )

    expires = (
        datetime.now() +
        timedelta(
            seconds=FILE_LIFETIME
        )
    )

    cursor.execute(
        """
        INSERT INTO files
        (
            owner_id,
            folder,
            file_id,
            file_name,
            code,
            created_at,
            expires
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            folder,
            message.document.file_id,
            encrypted_name,
            code,
            datetime.now().isoformat(),
            expires.isoformat()
        )
    )

    db.commit()

    username = (
        await bot.get_me()
    ).username

    link = (
        f"https://t.me/{username}?start={code}"
    )

    await message.answer(
        f"""
✅ Файл загружен

📂 Folder:
{folder}

🔗 LINK:
{link}
"""
    )

# =========================================================
# FILE MENU
# =========================================================

@dp.callback_query(
    F.data.startswith("file:")
)
async def file_menu(call: CallbackQuery):

    code = call.data.split(":")[1]

    cursor.execute(
        """
        SELECT file_name,
               favorite,
               downloads
        FROM files
        WHERE code=?
        """,
        (code,)
    )

    data = cursor.fetchone()

    if not data:
        return

    file_name, favorite, downloads = data

    real_name = decrypt_text(
        file_name
    )

    username = (
        await bot.get_me()
    ).username

    link = (
        f"https://t.me/{username}?start={code}"
    )

    star = "⭐" if favorite else "☆"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Share",
                    url=link
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{star} Favorite",
                    callback_data=f"fav:{code}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Delete",
                    callback_data=f"delete:{code}"
                )
            ]
        ]
    )

    await call.message.edit_text(
        f"""
📄 {real_name}

📥 Downloads:
{downloads}

🔗 LINK:
{link}
""",
        reply_markup=kb
    )

# =========================================================
# FAVORITE
# =========================================================

@dp.callback_query(
    F.data.startswith("fav:")
)
async def favorite(call: CallbackQuery):

    code = call.data.split(":")[1]

    cursor.execute(
        """
        SELECT favorite
        FROM files
        WHERE code=?
        """,
        (code,)
    )

    current = cursor.fetchone()[0]

    new = 0 if current else 1

    cursor.execute(
        """
        UPDATE files
        SET favorite=?
        WHERE code=?
        """,
        (
            new,
            code
        )
    )

    db.commit()

    await call.answer(
        "⭐ Updated"
    )

# =========================================================
# FAVORITES
# =========================================================

@dp.message(
    F.text == "⭐ Избранное"
)
async def favorites(message: Message):

    user_id = message.from_user.id

    cursor.execute(
        """
        SELECT file_name,
               code
        FROM files
        WHERE owner_id=?
        AND favorite=1
        """,
        (user_id,)
    )

    files = cursor.fetchall()

    if not files:

        await message.answer(
            "⭐ Пусто"
        )

        return

    buttons = []

    for file_name, code in files:

        real_name = decrypt_text(
            file_name
        )

        buttons.append([
            InlineKeyboardButton(
                text=f"⭐ {real_name}",
                callback_data=f"file:{code}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await message.answer(
        "⭐ Избранное:",
        reply_markup=kb
    )

# =========================================================
# DELETE
# =========================================================

@dp.callback_query(
    F.data.startswith("delete:")
)
async def delete(call: CallbackQuery):

    code = call.data.split(":")[1]

    cursor.execute(
        """
        DELETE FROM files
        WHERE code=?
        """,
        (code,)
    )

    db.commit()

    await call.message.edit_text(
        "🗑 Файл удалён"
    )

# =========================================================
# TEXT HANDLER
# =========================================================

@dp.message(F.text)
async def text_handler(message: Message):

    user_id = message.from_user.id
    text = message.text

    # =====================================================
    # CREATE FOLDER
    # =====================================================

    if user_id in folder_users:

        folder_users.remove(user_id)

        cursor.execute(
            """
            INSERT INTO folders
            (
                user_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                user_id,
                text
            )
        )

        db.commit()

        await message.answer(
            f"✅ Папка {text} создана"
        )

        return

    # =====================================================
    # SEARCH
    # =====================================================

    if user_id in search_users:

        search_users.remove(user_id)

        query = text.lower()

        cursor.execute(
            """
            SELECT file_name,
                   code
            FROM files
            WHERE owner_id=?
            """,
            (user_id,)
        )

        files = cursor.fetchall()

        buttons = []

        for file_name, code in files:

            real_name = decrypt_text(
                file_name
            )

            if query in real_name.lower():

                buttons.append([
                    InlineKeyboardButton(
                        text=f"📄 {real_name}",
                        callback_data=f"file:{code}"
                    )
                ])

        if not buttons:

            await message.answer(
                "❌ Ничего не найдено"
            )

            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=buttons
        )

        await message.answer(
            "🔎 Результаты:",
            reply_markup=kb
        )

        return

    # =====================================================
    # 2FA
    # =====================================================

    if user_id in waiting_2fa:

        data = waiting_2fa[user_id]

        if datetime.now() > data["expires"]:

            del waiting_2fa[user_id]

            await message.answer(
                "⌛ CODE истёк"
            )

            return

        attempts[user_id] += 1

        if attempts[user_id] >= MAX_ATTEMPTS:

            del waiting_2fa[user_id]

            await message.answer(
                "🚫 Слишком много попыток"
            )

            return

        if text != data["2fa"]:

            await message.answer(
                "❌ Неверный CODE"
            )

            return

        code = data["code"]

        cursor.execute(
            """
            SELECT file_id,
                   file_name
            FROM files
            WHERE code=?
            """,
            (code,)
        )

        file_data = cursor.fetchone()

        if not file_data:

            await message.answer(
                "❌ Файл удалён"
            )

            return

        file_id, file_name = file_data

        real_name = decrypt_text(
            file_name
        )

        cursor.execute(
            """
            UPDATE files
            SET downloads=downloads+1
            WHERE code=?
            """,
            (code,)
        )

        db.commit()

        await message.answer_document(
            file_id,
            caption=f"📦 {real_name}"
        )

        del waiting_2fa[user_id]

# =========================================================
# CLEANER
# =========================================================

async def cleaner():

    while True:

        cursor.execute(
            """
            SELECT code,
                   expires
            FROM files
            """
        )

        files = cursor.fetchall()

        for code, expires in files:

            expires = datetime.fromisoformat(
                expires
            )

            if datetime.now() > expires:

                cursor.execute(
                    """
                    DELETE FROM files
                    WHERE code=?
                    """,
                    (code,)
                )

                db.commit()

        await asyncio.sleep(10)

# =========================================================
# MAIN
# =========================================================

async def main():

    print("=" * 50)
    print("🔥 FILESHIELD CLOUD STARTED")
    print("=" * 50)

    asyncio.create_task(
        cleaner()
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(bot)

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(main())
