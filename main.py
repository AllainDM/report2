
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
import to_exel
from report_handler import ReportParser
from report_handler import ReportCalc

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
    if user_id in config.USERS:
        logger.info(f"Запрос от пользователя {user_id}")
        await message.answer("Привет! Я бот короче...")


# Основной обработчик сообщений. Отправка и запросы отчетов.
@dp.message()
async def echo_mess(message: types.Message):
    # Получим ид пользователя и сравним со списком разрешенных в файле конфига
    user_id = message.from_user.id
    group_id = message.chat.id
    group_id *= -1
    logger.info(f"chat_id {group_id}")
    logger.info(f"user_id {user_id}")
    t_o = ""
    if user_id in config.USERS or group_id in config.GROUPS:
        # Определим ТО по ид юзера в телеграм 1240018773
        # Приоритет группы потом юзеры?
        if group_id == config.GROUP_ID_WEST:
            t_o = "ТО Запад"
        elif group_id == config.GROUP_ID_NORTH:
            t_o = "ТО Север"
        elif group_id == config.GROUP_ID_SOUTH:
            t_o = "ТО Юг"
        elif group_id == config.GROUP_ID_EAST:
            t_o = "ТО Восток"
        elif user_id in config.USERS_IN_WEST:
            t_o = "ТО Запад"
        elif user_id in config.USERS_IN_NORTH:
            t_o = "ТО Север"
        elif user_id in config.USERS_IN_SOUTH:
            t_o = "ТО Юг"
        elif user_id in config.USERS_IN_EAST:
            t_o = "ТО Восток"

        # Пересчет даты под запрос.
        # TODO возможно стоит перенести логику определения даты. Убрать лишние определения.
        date_now = datetime.now()
        logger.info(f"Текущая дата: {date_now}")
        date_ago = date_now - timedelta(hours=config.HOUR)  # здесь мы выставляем минус 15 часов
        logger.info(f"Новая дата: {date_ago}")
        date_now_full = date_ago.strftime("%d.%m.%Y")
        date_now_no_year = date_ago.strftime("%d.%m")
        date_month_year = date_ago.strftime("%m.%Y")

        # Обработка текстовых команд.
        # Запрос выписок из отчетов с привлеченными
        if message.text.lower() == "привлеченные":
            # Для получения папки месяца привлеченных вычтем 8 дней(максимальный срок, когда они должны быть уже сданы)
            date_ago = date_ago - timedelta(8)
            date_now_full = date_ago.strftime("%d.%m.%Y")
            date_month_year = date_ago.strftime("%m.%Y")

        # Запрос недельного отчета.
        # TODO реализовать логику.
        elif message.text.lower() == "неделя":
            # Обработка запроса "неделя"
            pass

        # Запрос отчета, за указанное количество дней назад
        elif message.text.isdigit() and 1 <= int(message.text) <= config.MAX_REPORT_DAYS_AGO:
            # Для получения отчета только авторизованный админ
            if user_id in config.USERS:
                # Поправим дату под запрос
                days_to_subtract = int(message.text) - 1
                date_ago = date_ago - timedelta(days=days_to_subtract)
                logger.info(f"Новая дата: {date_ago}")
                date_now_full = date_ago.strftime("%d.%m.%Y")
                date_month_year = date_ago.strftime("%m.%Y")
                # Для отчета за день одна папка с текущей датой
                report_folders = [date_now_full]
                for report_folder in report_folders:
                    await message.answer(f"Готовим отчёт за {report_folder}")
                    if os.path.exists(f"files/{t_o}/{date_month_year}/{report_folder}"):
                        files = os.listdir(f"files/{t_o}/{date_month_year}/{report_folder}")
                        await message.answer(f"Найдено {len(files)} файл(ов).")
                        reports = ReportCalc(message=message, t_o=t_o, files=files,
                                             date_month_year=date_month_year, report_folder=report_folder)
                        await reports.process_report()
                    else:
                        await message.answer(f"Папка {report_folder} не найдена.")
            else:
                await message.answer("Вы не авторизованны")
                await message.answer(f"user_id {user_id}")

        # Обработка текста, для определения отчета мастеров.
        else:
            try:
                report = ReportParser(message, t_o, date_now_full, date_month_year)
                await report.process_report()

            except IndexError:
                logger.info("Тут видимо сообщение не относящееся к отчету.")



# Основная функция запуска бота
async def main():
    # Удаляем вебхук, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг
    logger.info("Бот запущен")
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
