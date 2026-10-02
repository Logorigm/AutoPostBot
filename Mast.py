import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InputMediaPhoto


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = "8986178743:AAGgIv1lx-4WDXNerX3j9jE8ERx8AFM1Ygc"

# ID пользователей, которым разрешено добавлять арты
ADMIN_IDS = {
    1769899996, # твой Telegram ID
    8370116310 # Telegram ID второго пользователя
}

# ID канала
CHANNEL_ID = -1001234567890

# Подпись к альбому
# Она будет кликабельной ссылкой
CAPTION = '<a href="https://t.me/SecretOasisAll">Наши каналы</a>'
# Интервал между альбомами
INTERVAL_HOURS = 3

# Количество картинок в одном альбоме
POSTS_PER_BATCH = 4

# База данных
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

db = sqlite3.connect(
    DATABASE,
    check_same_thread=False
)

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

    # Последняя незапубликованная картинка
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

        # Сколько картинок уже находится
        # в последнем альбоме
        cursor.execute("""
            SELECT COUNT(*)
            FROM queue
            WHERE scheduled_at = ?
            AND posted = 0
        """, (last_time,))

        count = cursor.fetchone()[0]

        if count < POSTS_PER_BATCH:

            # В последний альбом ещё можно добавить
            scheduled_at = last_time

        else:

            # Создаём следующий альбом
            scheduled_at = (
                last_time +
                INTERVAL_HOURS * 60 * 60
            )

    cursor.execute("""
        INSERT INTO queue (
            file_id,
            scheduled_at
        )
        VALUES (?, ?)
    """, (
        file_id,
        scheduled_at
    ))

    db.commit()


# ============================================================
# ПОЛУЧИТЬ ГОТОВЫЙ АЛЬБОМ
# ============================================================

def get_images_to_post():

    now = current_time()

    # Сначала узнаём время самого старого альбома
    cursor.execute("""
        SELECT scheduled_at
        FROM queue
        WHERE posted = 0
        GROUP BY scheduled_at
        ORDER BY scheduled_at ASC
        LIMIT 1
    """)

    result = cursor.fetchone()

    if result is None:
        return []

    scheduled_at = result[0]

    # Проверяем, наступило ли время публикации
    if scheduled_at > now:
        return []

    # Получаем картинки именно этого альбома
    cursor.execute("""
        SELECT id, file_id
        FROM queue
        WHERE posted = 0
        AND scheduled_at = ?
        ORDER BY id ASC
        LIMIT ?
    """, (
        scheduled_at,
        POSTS_PER_BATCH
    ))

    images = cursor.fetchall()

    # Публикуем только полный альбом из 4 картинок
    if len(images) < POSTS_PER_BATCH:
        return []

    return images


# ============================================================
# ПОМЕТИТЬ КАК ОПУБЛИКОВАННЫЕ
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
# ПРОВЕРКА АДМИНА
# ============================================================

def is_admin(message: Message):

    return (
        message.from_user is not None
        and message.from_user.id in ADMIN_IDS
    )


# ============================================================
# BOT
# ============================================================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


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
# ПОЛУЧЕНИЕ КАРТИНКИ
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
        f"Арт добавлен в очередь.\n"
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
                    f"Готов альбом из {len(images)} картинок"
                )

                media = []

                # Создаём альбом
                for index, (image_id, file_id) in enumerate(images):

                    # Подпись добавляем только к первой картинке
                    caption = (
                        CAPTION
                        if index == 0
                        else None
                    )

                    media.append(
                        InputMediaPhoto(
                            media=file_id,
                            caption=caption,
                            parse_mode="HTML"
                        )
                    )

                try:

                    # Публикуем одним альбомом
                    await bot.send_media_group(
                        chat_id=CHANNEL_ID,
                        media=media
                    )

                    # Отмечаем все 4 картинки
                    # как опубликованные
                    for image_id, _ in images:
                        mark_as_posted(image_id)

                    logging.info(
                        "Альбом успешно опубликован"
                    )

                except Exception as error:

                    logging.error(
                        f"Ошибка публикации альбома: {error}"
                    )

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

    # Запускаем Telegram
    await dp.start_polling(bot)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
