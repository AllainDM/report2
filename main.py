
import os
import time
import json
import shutil
import asyncio
import logging
from datetime import datetime, timedelta

import xlwt
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

import config
import parser

# Настройка логирования
logging.basicConfig(level=logging.INFO)

logging.debug("Это отладочное сообщение")
logging.info("Это информационное сообщение")
logging.warning("Это предупреждение")
logging.error("Это ошибка")
logging.critical("Это критическая ошибка")

logger = logging.getLogger(__name__)

load_dotenv()
BOT_API_TOKEN = os.getenv("BOT_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_API_TOKEN)
dp = Dispatcher()

if not os.path.exists(f"files"):
    os.makedirs(f"files")
if not os.path.exists(f"files/ТО Запад"):
    os.makedirs(f"files/ТО Запад")
if not os.path.exists(f"files/ТО Север"):
    os.makedirs(f"files/ТО Север")
if not os.path.exists(f"files/ТО Юг"):
    os.makedirs(f"files/ТО Юг")
if not os.path.exists(f"files/ТО Восток"):
    os.makedirs(f"files/ТО Восток")


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Узнаем ид пользователя.
    user_id = message.from_user.id
    # Авторизация
    if user_id in config.users:
        logger.info(f"Запрос от пользователя {user_id}")
        await message.answer("Привет! Я бот короче...")


@dp.message()
async def echo_mess(message: types.Message):
    # Получим ид пользователя и сравним со списком разрешенных в файле конфига
    user_id = message.from_user.id
    group_id = message.chat.id
    group_id *= -1
    logger.info(f"chat_id {group_id}")
    logger.info(f"user_id {user_id}")
    t_o = ""
    if user_id in config.users or group_id in config.groups:
        # Определим ТО по ид юзера в телеграм 1240018773
        # Приоритет группы потом юзеры?
        if group_id == config.group_id_west:
            t_o = "ТО Запад"
        elif group_id == config.group_id_north:
            t_o = "ТО Север"
        elif group_id == config.group_id_south:
            t_o = "ТО Юг"
        elif group_id == config.group_id_east:
            t_o = "ТО Восток"
        elif user_id in config.users_in_west:
            t_o = "ТО Запад"
        elif user_id in config.users_in_north:
            t_o = "ТО Север"
        elif user_id in config.users_in_south:
            t_o = "ТО Юг"
        elif user_id in config.users_in_east:
            t_o = "ТО Восток"


# Основная функция запуска бота
async def main():
    # Удаляем вебхук, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг
    logger.info("Бот запущен")
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
