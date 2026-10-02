import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = "8986178743:AAGgIv1lx-4WDXNerX3j9jE8ERx8AFM1Ygc"

# Твой Telegram ID
ADMIN_ID = 1769899996

# ID Telegram-канала
CHANNEL_ID = -1003521280801

# Подпись под каждой картинкой
# Текст "Больше артов здесь" будет синей кликабельной ссылкой
CAPTION = '<a href="https://t.me/SecretOasisAll">Наши каналы</a>'

# Интервал между группами публикаций
INTERVAL_HOURS = 3

# Сколько картинок публиковать за один слот
POSTS_PER_BATCH = 4

# Файл базы данных
DATABASE = "bot.db"


# ============================================================
# ЛОГИ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ============================================================
# БАЗА ДАННЫХ
# ============================================================

db = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,
    scheduled_at INTEGER NOT NULL,
    posted INTEGER NOT NULL DEFAULT 0
)
""")

db.commit()


# ============================================================
# ВРЕМЯ
# ============================================================

def current_time():
    return int(datetime.now().timestamp())


# ============================================================
# ДОБАВЛЕНИЕ КАРТИНКИ В ОЧЕРЕДЬ
# ============================================================

def add_image(file_id):
    """
    Добавляет картинку в конец очереди.

    Первые 4 картинки получают одно время публикации.
    Следующие 4 — через 3 часа.
    И т.д.
    """

    cursor.execute("""
        SELECT scheduled_at
        FROM queue
        WHERE posted = 0
        ORDER BY scheduled_at DESC, id DESC
        LIMIT 1
    """)

    result = cursor.fetchone()

    # Если очередь пустая
    if result is None:

        scheduled_at = current_time()

    else:

        last_time = result[0]

        # Сколько картинок уже запланировано
        # на последний слот
        cursor.execute("""
            SELECT COUNT(*)
            FROM queue
            WHERE scheduled_at = ?
            AND posted = 0
        """, (last_time,))

        count = cursor.fetchone()[0]

        if count < POSTS_PER_BATCH:

            # В последнем слоте ещё есть место
            scheduled_at = last_time

        else:

            # Последний слот заполнен.
            # Создаём следующий через 3 часа.
            scheduled_at = (
                last_time +
                INTERVAL_HOURS * 60 * 60
            )

    cursor.execute("""
        INSERT INTO queue (file_id, scheduled_at)
        VALUES (?, ?)
    """, (file_id, scheduled_at))

    db.commit()


# ============================================================
# ПОЛУЧИТЬ КАРТИНКИ ДЛЯ ПУБЛИКАЦИИ
# ============================================================

def get_images_to_post():

    now = current_time()

    cursor.execute("""
        SELECT id, file_id
        FROM queue
        WHERE posted = 0
        AND scheduled_at <= ?
        ORDER BY id ASC
        LIMIT ?
    """, (
        now,
        POSTS_PER_BATCH
    ))

    return cursor.fetchall()


# ============================================================
# ПОМЕТИТЬ КАРТИНКУ КАК ОПУБЛИКОВАННУЮ
# ============================================================

def mark_as_posted(image_id):

    cursor.execute("""
        UPDATE queue
        SET posted = 1
        WHERE id = ?
    """, (image_id,))

    db.commit()


# ============================================================
# КОЛИЧЕСТВО КАРТИНОК В ОЧЕРЕДИ
# ============================================================

def get_queue_count():

    cursor.execute("""
        SELECT COUNT(*)
        FROM queue
        WHERE posted = 0
    """)

    return cursor.fetchone()[0]


# ============================================================
# BOT
# ============================================================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# ПРОВЕРКА АДМИНА
# ============================================================

def is_admin(message: Message):

    return (
        message.from_user is not None
        and message.from_user.id == ADMIN_ID
    )


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):

    if not is_admin(message):
        return

    count = get_queue_count()

    await message.answer(
        f"Бот работает.\n\n"
        f"Артов в очереди: {count}"
    )


# ============================================================
# ПОЛУЧЕНИЕ ОДНОЙ КАРТИНКИ
# ============================================================

@dp.message(F.photo)
async def receive_photo(message: Message):

    if not is_admin(message):
        return

    # Фото максимального качества
    photo = message.photo[-1]

    add_image(photo.file_id)

    count = get_queue_count()

    await message.answer(
        f"Арти добавлен в очередь.\n"
        f"Сейчас в очереди: {count}"
    )


# ============================================================
# ПУБЛИКАТОР
# ============================================================

async def publisher():

    while True:

        try:

            images = get_images_to_post()

            if images:

                logging.info(
                    f"Найдено для публикации: {len(images)}"
                )

                for image_id, file_id in images:

                    try:

                        await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=file_id,
                            caption=CAPTION,
                            parse_mode="HTML"
                        )

                        mark_as_posted(image_id)

                        logging.info(
                            f"Картинка {image_id} опубликована"
                        )

                    except Exception as error:

                        logging.error(
                            f"Ошибка публикации "
                            f"{image_id}: {error}"
                        )

                        # Не помечаем как опубликованную.
                        # Попробуем ещё раз при следующем цикле.
                        break

            # Проверяем очередь каждые 30 секунд
            await asyncio.sleep(30)

        except Exception as error:

            logging.error(
                f"Ошибка планировщика: {error}"
            )

            await asyncio.sleep(30)


# ============================================================
# ЗАПУСК
# ============================================================

async def main():

    logging.info("Бот запускается...")

    # Запускаем планировщик
    asyncio.create_task(
        publisher()
    )

    # Запускаем Telegram-бота
    await dp.start_polling(bot)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())
