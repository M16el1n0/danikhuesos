#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот для приёма анкет моделей.
Анкета: имя, город, телефон, дата рождения, уровень английского (0-10),
проживание (одна/не одна), устройства (2 телефона / комп + телефон),
модель устройства, часы/дни в неделю, наушники, telegram для связи,
2 фото (в анфас и полный рост).

Требуется: pip install python-telegram-bot
Переменные окружения:
  BOT_TOKEN        - токен бота от @BotFather (обязательно)
  ADMIN_CHAT_ID    - ID чата/канала, куда присылать готовые анкеты (опционально)
"""

import logging
import os
import re
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------- настройка
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # может быть None

DB_PATH = os.getenv("DB_PATH", "applications.db")
PHOTOS_DIR = os.getenv("PHOTOS_DIR", "photos")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Добавь его в переменные окружения или .env")

os.makedirs(PHOTOS_DIR, exist_ok=True)

# ---------------------------------------------------------------- база данных
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            city TEXT,
            phone TEXT,
            dob TEXT,
            english INTEGER,
            living TEXT,
            devices TEXT,
            device_model TEXT,
            hours_days TEXT,
            headphones TEXT,
            contact_tg TEXT,
            photo_face TEXT,
            photo_full TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_application(data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO applications
        (user_id, username, name, city, phone, dob, english, living, devices,
         device_model, hours_days, headphones, contact_tg, photo_face, photo_full, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("user_id"),
            data.get("username"),
            data.get("name"),
            data.get("city"),
            data.get("phone"),
            data.get("dob"),
            data.get("english"),
            data.get("living"),
            data.get("devices"),
            data.get("device_model"),
            data.get("hours_days"),
            data.get("headphones"),
            data.get("contact_tg"),
            data.get("photo_face"),
            data.get("photo_full"),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


# ---------------------------------------------------------------- состояния
(
    NAME,
    CITY,
    PHONE,
    DOB,
    ENGLISH,
    LIVING,
    DEVICES,
    DEVICE_MODEL,
    HOURS_DAYS,
    HEADPHONES,
    CONTACT,
    PHOTO_FACE,
    PHOTO_FULL,
) = range(13)

# ---------------------------------------------------------------- клавиатуры
LIVING_KEYBOARD = ReplyKeyboardMarkup(
    [["Одна", "Не одна"]], one_time_keyboard=True, resize_keyboard=True
)
DEVICES_KEYBOARD = ReplyKeyboardMarkup(
    [["2 мобильных телефона", "Компьютер + телефон"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)
HEADPHONES_KEYBOARD = ReplyKeyboardMarkup(
    [["Есть", "Нет"]], one_time_keyboard=True, resize_keyboard=True
)

PHONE_RE = re.compile(r"^[\d\s\+\-\(\)]{7,25}$")


def valid_phone(text: str) -> bool:
    return bool(PHONE_RE.match(text.strip()))


def valid_dob(text: str) -> str | None:
    """Возвращает нормализованную дату ДД.ММ.ГГГГ или None."""
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- хендлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    context.user_data.clear()
    context.user_data["user_id"] = user.id
    context.user_data["username"] = user.username or user.full_name

    text = (
        "Привет! 👋 Я помогаю оформить анкету для модели.\n\n"
        "Заполним по порядку. Начнём с первого пункта.\n\n"
        "<b>1. Имя</b>\nКак тебя зовут?"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return NAME


async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("<b>2. Город</b>\nИз какого ты города?",
                                    parse_mode=ParseMode.HTML)
    return CITY


async def city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["city"] = update.message.text.strip()
    await update.message.reply_text(
        "<b>3. Номер телефона</b>\nНапиши номер в любом удобном формате.",
        parse_mode=ParseMode.HTML,
    )
    return PHONE


async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not valid_phone(text):
        await update.message.reply_text(
            "Похоже, это не похоже на номер телефона. Попробуй ещё раз "
            "(пример: +7 900 123-45-67)."
        )
        return PHONE
    context.user_data["phone"] = text
    await update.message.reply_text(
        "<b>4. Дата рождения</b>\nНапиши в формате ДД.ММ.ГГГГ (пример: 01.05.1995).",
        parse_mode=ParseMode.HTML,
    )
    return DOB


async def dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    normalized = valid_dob(update.message.text)
    if not normalized:
        await update.message.reply_text(
            "Не понял дату. Напиши в формате ДД.ММ.ГГГГ (пример: 01.05.1995)."
        )
        return DOB
    context.user_data["dob"] = normalized
    await update.message.reply_text(
        "<b>5. Знания английского</b>\nОцени от 0 до 10, где 0 — не знаю, "
        "10 — свободно владею. Пришли одну цифру.",
        parse_mode=ParseMode.HTML,
    )
    return ENGLISH


async def english(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit() or not (0 <= int(text) <= 10):
        await update.message.reply_text("Пришли одну цифру от 0 до 10.")
        return ENGLISH
    context.user_data["english"] = int(text)
    await update.message.reply_text(
        "<b>6. Проживание</b>\nТы живешь одна или не одна?",
        reply_markup=LIVING_KEYBOARD,
        parse_mode=ParseMode.HTML,
    )
    return LIVING


async def living(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in ("Одна", "Не одна"):
        await update.message.reply_text("Выбери вариант кнопкой ниже.")
        return LIVING
    context.user_data["living"] = update.message.text
    await update.message.reply_text(
        "<b>7. Устройства</b>\nЕсть ли у тебя 2 мобильных телефона "
        "или компьютер + телефон?",
        reply_markup=DEVICES_KEYBOARD,
        parse_mode=ParseMode.HTML,
    )
    return DEVICES


async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in ("2 мобильных телефона", "Компьютер + телефон"):
        await update.message.reply_text("Выбери вариант кнопкой ниже.")
        return DEVICES
    context.user_data["devices"] = update.message.text
    await update.message.reply_text(
        "<b>8. Модель устройства</b>\nС какого устройства будешь работать? "
        "(например, iPhone 13, Samsung A53, ноутбук ASUS и т.д.)",
        parse_mode=ParseMode.HTML,
    )
    return DEVICE_MODEL


async def device_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["device_model"] = update.message.text.strip()
    await update.message.reply_text(
        "<b>9. Время на работу</b>\nСколько часов и дней в неделю ты готова "
        "уделять работе? (например, 4 часа в день, 5 дней в неделю)",
        parse_mode=ParseMode.HTML,
    )
    return HOURS_DAYS


async def hours_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["hours_days"] = update.message.text.strip()
    await update.message.reply_text(
        "<b>10. Наушники</b>\nЕсть ли у тебя наушники?",
        reply_markup=HEADPHONES_KEYBOARD,
        parse_mode=ParseMode.HTML,
    )
    return HEADPHONES


async def headphones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in ("Есть", "Нет"):
        await update.message.reply_text("Выбери вариант кнопкой ниже.")
        return HEADPHONES
    context.user_data["headphones"] = update.message.text
    await update.message.reply_text(
        "<b>11. Телеграм для связи</b>\nПришли свой username в телеграме "
        "(с @ или без).",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML,
    )
    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.startswith("@"):
        text = "@" + text
    context.user_data["contact_tg"] = text
    await update.message.reply_text(
        "<b>12. Фото в анфас</b>\nПришли одно фото, на котором хорошо видно лицо.",
        parse_mode=ParseMode.HTML,
    )
    return PHOTO_FACE


async def photo_face(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Пришли, пожалуйста, именно фото.")
        return PHOTO_FACE
    file_id = update.message.photo[-1].file_id
    context.user_data["photo_face_file_id"] = file_id
    await update.message.reply_text(
        "<b>13. Фото в полный рост</b>\nПришли одно фото в полный рост.",
        parse_mode=ParseMode.HTML,
    )
    return PHOTO_FULL


async def photo_full(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Пришли, пожалуйста, именно фото.")
        return PHOTO_FULL

    data = context.user_data
    file_id = update.message.photo[-1].file_id

    # скачиваем фото
    face_file = await context.bot.get_file(data["photo_face_file_id"])
    full_file = await context.bot.get_file(file_id)

    face_path = os.path.join(
        PHOTOS_DIR, f"{data['user_id']}_face_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
    )
    full_path = os.path.join(
        PHOTOS_DIR, f"{data['user_id']}_full_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
    )
    await face_file.download_to_drive(face_path)
    await full_file.download_to_drive(full_path)

    data["photo_face"] = face_path
    data["photo_full"] = full_path

    app_id = save_application(data)

    # подтверждение пользователю
    summary = format_application(data, app_id)
    await update.message.reply_text(
        "Анкета принята! ✅ Спасибо, с тобой свяжутся.\n\n" + summary,
        parse_mode=ParseMode.HTML,
    )

    # пересылка админу
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                ADMIN_CHAT_ID,
                "Новая анкета модели #{}:\n{}".format(app_id, summary),
                parse_mode=ParseMode.HTML,
            )
            await context.bot.send_photo(ADMIN_CHAT_ID, photo=data["photo_face_file_id"],
                                         caption="Фото в анфас (анкета #{})".format(app_id))
            await context.bot.send_photo(ADMIN_CHAT_ID, photo=file_id,
                                         caption="Фото в полный рост (анкета #{})".format(app_id))
        except Exception as e:
            log.exception("Не удалось отправить анкету админу: %s", e)

    context.user_data.clear()
    return ConversationHandler.END


def format_application(data: dict, app_id: int) -> str:
    return (
        f"<b>Анкета №{app_id}</b>\n"
        f"👤 Имя: {data.get('name')}\n"
        f"🏙 Город: {data.get('city')}\n"
        f"📞 Телефон: {data.get('phone')}\n"
        f"🎂 Дата рождения: {data.get('dob')}\n"
        f"🇬🇧 Английский: {data.get('english')}/10\n"
        f"🏠 Проживание: {data.get('living')}\n"
        f"📱 Устройства: {data.get('devices')}\n"
        f"💻 Модель устройства: {data.get('device_model')}\n"
        f"⏰ Часы/дни в неделю: {data.get('hours_days')}\n"
        f"🎧 Наушники: {data.get('headphones')}\n"
        f"✉️ Телеграм: {data.get('contact_tg')}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Заполнение отменено. Чтобы начать заново — /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Команда не распознана. Напиши /start, чтобы заполнить анкету.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке обновления: %s", context.error)


def build_application() -> Application:
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, dob)],
            ENGLISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, english)],
            LIVING: [MessageHandler(filters.TEXT & ~filters.COMMAND, living)],
            DEVICES: [MessageHandler(filters.TEXT & ~filters.COMMAND, devices)],
            DEVICE_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, device_model)],
            HOURS_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, hours_days)],
            HEADPHONES: [MessageHandler(filters.TEXT & ~filters.COMMAND, headphones)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
            PHOTO_FACE: [MessageHandler(filters.PHOTO, photo_face)],
            PHOTO_FULL: [MessageHandler(filters.PHOTO, photo_full)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv)
    application.add_handler(CommandHandler("help", unknown))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    app = build_application()
    log.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
