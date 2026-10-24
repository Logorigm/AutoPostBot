import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InputMediaPhoto


# ============================================================
# НАСТРОЙКИ
# ============================================================

# <<< ИЗМЕНИТЬ >>>
# Токен, который выдаёт @BotFather
BOT_TOKEN = "8986178743:AAGgIv1lx-4WDXNerX3j9jE8ERx8AFM1Ygc"


# <<< ИЗМЕНИТЬ >>>
# Telegram ID пользователей, которым разрешено
# добавлять арты и использовать команды бота
ADMIN_IDS = {
    1769899996, 
    8370116310,
    7819336369,
    6530117523,
    7252589882
}


# <<< ИЗМЕНИТЬ >>>
# ID Telegram-канала
CHANNEL_ID = -1003521280801


# <<< ИЗМЕНИТЬ >>>
# Ссылка и текст подписи.
# "Больше артов здесь" будет синей кликабельной ссылкой.
CAPTION =  '<a href="https://t.me/RashodnikAll">Наши каналы</a>'


# Интервал между автоматическими публикациями
INTERVAL_HOURS = 3


# Количество картинок в одном альбоме
POSTS_PER_BATCH = 2


# Название файла базы данных
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

# Здесь хранится время следующей
# автоматической публикации
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
)
""")

db.commit()


# ============================================================
# ТЕКУЩЕЕ ВРЕМЯ
# ============================================================

def current_time():
    return int(datetime.now().timestamp())


# ============================================================
# ДОБАВЛЕНИЕ КАРТИНКИ В ОЧЕРЕДЬ
# ============================================================

def add_image(file_id):

    # scheduled_at теперь хранит время добавления арта.
    # Порядок публикации случайный,
    # а время — общее расписание (см. ниже).
    cursor.execute("""
        INSERT INTO queue (
            file_id,
            scheduled_at
        )
        VALUES (?, ?)
    """, (
        file_id,
        current_time()
    ))

    db.commit()


# ============================================================
# РАСПИСАНИЕ ПУБЛИКАЦИЙ
# ============================================================

def set_next_post_time(timestamp):

    cursor.execute("""
        INSERT OR REPLACE INTO settings (
            key,
            value
        )
        VALUES ('next_post_at', ?)
    """, (timestamp,))

    db.commit()


def get_next_post_time():

    cursor.execute("""
        SELECT value
        FROM settings
        WHERE key = 'next_post_at'
    """)

    result = cursor.fetchone()


    if result is not None:
        return result[0]


    # Первый запуск после обновления.
    # Берём время ближайшего альбома из старой очереди,
    # чтобы не сбить уже запланированную публикацию.
    cursor.execute("""
        SELECT MIN(scheduled_at)
        FROM queue
        WHERE posted = 0
    """)

    next_post_at = cursor.fetchone()[0] or current_time()

    set_next_post_time(next_post_at)

    return next_post_at


# Следующая публикация — через INTERVAL_HOURS
def schedule_next_post():

    set_next_post_time(
        current_time() +
        INTERVAL_HOURS * 60 * 60
    )


# ============================================================
# ПОЛУЧЕНИЕ СЛУЧАЙНОГО АЛЬБОМА
# ============================================================

def get_images_to_post(force=False):

    # При обычной публикации проверяем время.
    #
    # При /next force=True,
    # поэтому время игнорируется.
    if not force and get_next_post_time() > current_time():
        return []


    # Выбираем случайные арты из всей очереди
    cursor.execute("""
        SELECT id, file_id
        FROM queue
        WHERE posted = 0
        ORDER BY RANDOM()
        LIMIT ?
    """, (POSTS_PER_BATCH,))

    images = cursor.fetchall()


    # Публикуем только полный альбом
    # из POSTS_PER_BATCH картинок
    if len(images) < POSTS_PER_BATCH:
        return []


    return images


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
# КОЛИЧЕСТВО АРТОВ В ОЧЕРЕДИ
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
# СОЗДАНИЕ АЛЬБОМА
# ============================================================

def create_media_group(images):

    media = []


    for index, (image_id, file_id) in enumerate(images):

        # Подпись только у первой картинки
        caption = CAPTION if index == 0 else None


        media.append(
            InputMediaPhoto(
                media=file_id,
                caption=caption,
                parse_mode="HTML"
            )
        )


    return media


# ============================================================
# BOT
# ============================================================

bot = Bot(BOT_TOKEN)

dp = Dispatcher()


# ============================================================
# /start
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):

    if not is_admin(message):
        return


    count = get_queue_count()


    await message.answer(
        f"Бот работает.\n\n"
        f"Артов в очереди: {count}\n\n"
        f"/next — опубликовать {POSTS_PER_BATCH} случайных арта сейчас"
    )


# ============================================================
# /next
# ============================================================

@dp.message(Command("next"))
async def next_album(message: Message):

    if not is_admin(message):
        return


    # force=True означает:
    # не обращаем внимания на время публикации
    images = get_images_to_post(force=True)


    if not images:

        count = get_queue_count()

        if count == 0:

            await message.answer(
                "Очередь пуста."
            )

        else:

            await message.answer(
                f"Пока нет полного альбома из {POSTS_PER_BATCH} артов."
            )

        return


    # Создаём альбом
    media = create_media_group(images)


    try:

        # Отправляем картинки одним альбомом
        await bot.send_media_group(
            chat_id=CHANNEL_ID,
            media=media
        )


        # Отмечаем все картинки как опубликованные
        for image_id, _ in images:

            mark_as_posted(image_id)


        # Следующий автопост — через INTERVAL_HOURS
        schedule_next_post()


        await message.answer(
            f"Следующие {POSTS_PER_BATCH} арта опубликованы."
        )


        logging.info(
            "Альбом опубликован вручную через /next"
        )


    except Exception as error:

        logging.error(
            f"Ошибка ручной публикации: {error}"
        )


        await message.answer(
            "Ошибка при публикации альбома."
        )


# ============================================================
# ПОЛУЧЕНИЕ КАРТИНКИ
# ============================================================

@dp.message(F.photo)
async def receive_photo(message: Message):

    if not is_admin(message):
        return


    # Берём изображение максимального качества
    photo = message.photo[-1]


    # Добавляем в очередь
    add_image(photo.file_id)


    # Показываем количество оставшихся артов
    count = get_queue_count()


    await message.answer(
        f"Арт добавлен в очередь.\n"
        f"Сейчас в очереди: {count}"
    )


# ============================================================
# АВТОМАТИЧЕСКАЯ ПУБЛИКАЦИЯ
# ============================================================

async def publisher():

    while True:

        try:

            # Обычная публикация.
            # force=False — время учитывается.
            images = get_images_to_post(
                force=False
            )


            if images:

                logging.info(
                    f"Готов альбом из {len(images)} картинок"
                )


                # Создаём альбом
                media = create_media_group(
                    images
                )


                try:

                    # Публикуем альбом
                    await bot.send_media_group(
                        chat_id=CHANNEL_ID,
                        media=media
                    )


                    # Отмечаем картинки
                    # как опубликованные
                    for image_id, _ in images:

                        mark_as_posted(
                            image_id
                        )


                    # Следующий автопост —
                    # через INTERVAL_HOURS
                    schedule_next_post()


                    logging.info(
                        "Альбом автоматически опубликован"
                    )


                except Exception as error:

                    logging.error(
                        f"Ошибка публикации: {error}"
                    )


            # Проверяем очередь каждые 30 секунд
            await asyncio.sleep(30)


        except Exception as error:

            logging.error(
                f"Ошибка планировщика: {error}"
            )

            await asyncio.sleep(30)


# ============================================================
# ЗАПУСК БОТА
# ============================================================

async def main():

    logging.info(
        "Бот запускается..."
    )


    # Запускаем автоматический планировщик
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
