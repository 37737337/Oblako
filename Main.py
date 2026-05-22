# =========================================================
# FILESHIELD CLOUD ULTIMATE
# FINAL VERSION
# =========================================================

import asyncio
import sqlite3
import random
import os
import pyotp

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
# CONFIG
# =========================================================

FILE_LIFETIME = 3600
TWOFA_LIFETIME = 30
MAX_ATTEMPTS = 3

# =========================================================
# BOT
# =========================================================

bot = Bot(TOKEN)

dp = Dispatcher()

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

# users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    premium INTEGER DEFAULT 0,
    totp_secret TEXT
)
""")

# folders
cursor.execute("""
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    parent TEXT
)
""")

# files
cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    folder TEXT,
    file_id TEXT,
    file_name TEXT,
    code TEXT,
    tags TEXT,
    favorite INTEGER,
    downloads INTEGER DEFAULT 0,
    created_at TEXT,
    expires TEXT
)
""")

db.commit()

# =========================================================
# STATES
# =========================================================

upload_mode = set()

create_folder_mode = set()

search_mode = set()

waiting_2fa = {}

attempts = {}

current_folder = {}

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
        ],
        [
            KeyboardButton(
                text="🔑 TOTP"
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
        for _ in range(10)
    )

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

🛡 2FA:
{twofa}

⏳ 30 секунд
"""
        )

        await message.answer(
            """
🛡 Запрос отправлен владельцу

Введите 2FA CODE:
"""
        )

        return

    # =====================================================
    # NORMAL START
    # =====================================================

    await message.answer(
        """
🔥 FILESHIELD CLOUD

☁️ Telegram Cloud
📂 Folders
🔐 Secure Share
🛡 Owner 2FA
🔎 Search
⭐ Favorites
🔒 Encryption
""",
        reply_markup=main_kb
    )

# =========================================================
# CREATE FOLDER
# =========================================================

@dp.message(
    F.text == "➕ Папка"
)
async def create_folder(message: Message):

    create_folder_mode.add(
        message.from_user.id
    )

    folder = current_folder.get(
        message.from_user.id,
        "root"
    )

    await message.answer(
        f"""
📂 Current folder:
{folder}

Введите название:
"""
    )

# =========================================================
# SEARCH
# =========================================================

@dp.message(
    F.text == "🔎 Поиск"
)
async def search(message: Message):

    search_mode.add(
        message.from_user.id
    )

    await message.answer(
        "🔎 Введите запрос:"
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
            "⭐ Избранное пусто"
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
# TOTP
# =========================================================

@dp.message(
    F.text == "🔑 TOTP"
)
async def totp(message: Message):

    secret = pyotp.random_base32()

    cursor.execute(
        """
        INSERT OR REPLACE INTO users
        (
            user_id,
            totp_secret
        )
        VALUES (?, ?)
        """,
        (
            message.from_user.id,
            secret
        )
    )

    db.commit()

    await message.answer(
        f"""
🔑 TOTP ENABLED

SECRET:
{secret}

Добавьте в:
Google Authenticator
"""
    )

# =========================================================
# INPUT HANDLER
# =========================================================

@dp.message()
async def input_handler(message: Message):

    user_id = message.from_user.id

    # =====================================================
    # CREATE FOLDER
    # =====================================================

    if user_id in create_folder_mode:

        create_folder_mode.remove(
            user_id
        )

        folder_name = message.text

        parent = current_folder.get(
            user_id,
            "root"
        )

        cursor.execute(
            """
            INSERT INTO folders
            (
                user_id,
                name,
                parent
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                folder_name,
                parent
            )
        )

        db.commit()

        await message.answer(
            f"""
✅ Папка создана

📂 {folder_name}
"""
        )

        return

    # =====================================================
    # SEARCH
    # =====================================================

    if user_id in search_mode:

        search_mode.remove(
            user_id
        )

        query = message.text.lower()

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
                "⌛ 2FA истёк"
            )

            return

        attempts[user_id] += 1

        if attempts[user_id] >= MAX_ATTEMPTS:

            del waiting_2fa[user_id]

            await message.answer(
                "🚫 Слишком много попыток"
            )

            return

        if message.text != data["2fa"]:

            await message.answer(
                f"""
❌ Неверный 2FA

Осталось:
{MAX_ATTEMPTS - attempts[user_id]}
"""
            )

            return

        code = data["code"]

        cursor.execute(
            """
            SELECT file_id,
                   file_name,
                   downloads
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

        file_id, file_name, downloads = file_data

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

        return

# =========================================================
# CLOUD
# =========================================================

@dp.message(
    F.text == "☁️ Облако"
)
async def cloud(message: Message):

    user_id = message.from_user.id

    parent = current_folder.get(
        user_id,
        "root"
    )

    cursor.execute(
        """
        SELECT name
        FROM folders
        WHERE user_id=?
        AND parent=?
        """,
        (
            user_id,
            parent
        )
    )

    folders = cursor.fetchall()

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
            parent
        )
    )

    files = cursor.fetchall()

    buttons = []

    for folder in folders:

        buttons.append([
            InlineKeyboardButton(
                text=f"📂 {folder[0]}",
                callback_data=f"open:{folder[0]}"
            )
        ])

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

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await message.answer(
        f"☁️ Folder: {parent}",
        reply_markup=kb
    )

# =========================================================
# OPEN FOLDER
# =========================================================

@dp.callback_query(
    F.data.startswith("open:")
)
async def open_folder(call: CallbackQuery):

    folder = call.data.split(":")[1]

    current_folder[
        call.from_user.id
    ] = folder

    await cloud(call.message)

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
               downloads,
               created_at
        FROM files
        WHERE code=?
        """,
        (code,)
    )

    data = cursor.fetchone()

    if not data:
        return

    file_name, favorite, downloads, created_at = data

    real_name = decrypt_text(
        file_name
    )

    username = (
        await bot.get_me()
    ).username

    link = (
        f"https://t.me/"
        f"{username}"
        f"?start={code}"
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
                    text="📈 Stats",
                    callback_data=f"stats:{code}"
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

🕒 Created:
{created_at}

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

    data = cursor.fetchone()

    if not data:
        return

    current = data[0]

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
        "⭐ Обновлено"
    )

# =========================================================
# STATS
# =========================================================

@dp.callback_query(
    F.data.startswith("stats:")
)
async def stats(call: CallbackQuery):

    code = call.data.split(":")[1]

    cursor.execute(
        """
        SELECT file_name,
               downloads,
               created_at
        FROM files
        WHERE code=?
        """,
        (code,)
    )

    data = cursor.fetchone()

    if not data:
        return

    file_name, downloads, created_at = data

    real_name = decrypt_text(
        file_name
    )

    await call.message.answer(
        f"""
📄 {real_name}

📥 Downloads:
{downloads}

🕒 Created:
{created_at}
"""
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
# UPLOAD
# =========================================================

@dp.message(
    F.text == "📤 Загрузить"
)
async def upload(message: Message):

    upload_mode.add(
        message.from_user.id
    )

    folder = current_folder.get(
        message.from_user.id,
        "root"
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

    if user_id not in upload_mode:
        return

    upload_mode.remove(user_id)

    folder = current_folder.get(
        user_id,
        "root"
    )

    code = create_code()

    expires = (
        datetime.now() +
        timedelta(
            seconds=FILE_LIFETIME
        )
    )

    encrypted_name = encrypt_text(
        message.document.file_name
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
            tags,
            favorite,
            created_at,
            expires
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            folder,
            message.document.file_id,
            encrypted_name,
            code,
            "#default",
            0,
            datetime.now().isoformat(),
            expires.isoformat()
        )
    )

    db.commit()

    username = (
        await bot.get_me()
    ).username

    link = (
        f"https://t.me/"
        f"{username}"
        f"?start={code}"
    )

    await message.answer(
        f"""
✅ Файл загружен

📄 {message.document.file_name}

📂 Folder:
{folder}

🔗 LINK:
{link}

⏳ 1 hour
"""
    )

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
