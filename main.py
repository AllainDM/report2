
import os
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
from report_handler import ReportCalc
from report_handler import ReportWeek
from report_handler import ReportParser
from report_handler import MastersStatistic
from report_handler import OneMasterStatistic

# Настройка логирования
logging.basicConfig(level=logging.INFO)
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
        await message.answer("Привет! Я бот...")

# Статистика по мастерам одного ТО за месяц. !!! Внимание, это не аналог отчета за неделю.
@dp.message(Command("month", "месяц"))
async def month_stats(message: types.Message):
    # Узнаем ид пользователя.
    user_id = message.from_user.id
    # Для получения общей статистики только авторизованный админ
    if user_id in config.USERS:
        # Получим ТО по группе или по пользователю
        t_o = await get_to(message)
        if t_o:  # ТО должно быть, если пользователь уже определен, но для исключения ошибок
            await message.answer(f"📊 Подготовка статистики за месяц для {t_o}")
            month = await get_month_dates()  # Список всех дат в месяце
            statistic = MastersStatistic(message=message, t_o=t_o, month=month)
            await statistic.process_report()

# Статистика по выбранному мастеру за месяц.
@dp.message(Command("master", "мастер"))
async def month_stats(message: types.Message):
    # Получим ТО по группе или по пользователю
    t_o = await get_to(message)
    if t_o:  # Защита от незарегистрированных пользователей и чатов.
        args = message.text.split(maxsplit=1)  # Разделяем только на 2 части
        if len(args) > 1:
            one_master = args[1].title()
            await message.answer(f"📊 Подготовка статистики за месяц для {one_master}")
            month = await get_month_dates()  # Список всех дат в месяце
            statistic = OneMasterStatistic(message=message, one_master=one_master, month=month)
            await statistic.process_report()

# Удаление папки
@dp.message(Command("del"))
async def echo_mess(message: types.Message):
    # Узнаем ид пользователя.
    user_id = message.from_user.id
    # Получим ТО по группе или по пользователю
    t_o = await get_to(message)
    if t_o and user_id in config.USERS:  # Доступно только "админам"
        command = message.text.split(maxsplit=1)
        command = command[1]
        if len(command) == 18:
            await message.answer(f"Хотим удалить папку /{t_o}/{command}")
            try:
                shutil.rmtree(f"files/{t_o}/{command}")
                logger.info(f"/{t_o}/{command} удален")
                await message.answer(f"Папка /{t_o}/{command} удалена")
            except OSError as error:
                logger.info("Возникла ошибка1.")
                await message.answer(f"Папка /{t_o}/{command} не найдена!!!")
        else:
            await message.answer(f"Дата не указана или указана не верно")
    # else:
    #     await message.answer("Неа")

# Основной обработчик сообщений. Отправка и запросы отчетов.
@dp.message()
async def echo_mess(message: types.Message):
    user_id = message.from_user.id  # id пользователя, часть запросов разрешены только руководителям.
    # Получим ТО по группе или по пользователю
    t_o = await get_to(message)
    if t_o:  # Защита от незарегистрированных пользователей и чатов.
        # Пересчет даты под запрос.
        # TODO возможно стоит перенести логику определения даты. Убрать лишние определения.
        date_now = datetime.now()
        logger.info(f"Текущая дата: {date_now}")
        date_ago = date_now - timedelta(hours=config.HOUR)  # здесь мы выставляем минус 15 часов
        logger.info(f"Новая дата: {date_ago}")
        date_now_full = date_ago.strftime("%d.%m.%Y")
        date_month_year = date_ago.strftime("%m.%Y")

        # Обработка текстовых команд.
        # Запрос выписок из отчетов с привлеченными
        if message.text.lower() == "привлеченные":
            ...

        # Запрос недельного отчета.
        elif message.text.lower() == "неделя":
            # Для получения отчета только авторизованный админ
            if user_id in config.USERS:
                week = await get_last_full_week()  # Получение списка дат в неделе(для перебора папок)
                report = ReportWeek(message=message, t_o=t_o, week=week, date_month_year=date_month_year)
                await report.process_report()

        # Статистика по мастерам за месяц. !!! Внимание, это не аналог отчета за неделю.
        elif message.text.lower() == "месяц":
            # Для получения отчета только авторизованный админ
            if user_id in config.USERS:
                month = await get_month_dates()  # Получение списка дат в месяце(для перебора папок)
                statistic = MastersStatistic(message=message, t_o=t_o, month=month)
                await statistic.process_report()

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

# Составление списка дат для недельного отчета
async def get_last_full_week():
    # Получаем текущую дату
    today = datetime.now()
    # Определяем день недели (Понедельник=0, Вторник=1, ..., Воскресенье=6)
    today_weekday = today.weekday()
    # Вычисляем количество дней, чтобы вернуться к прошлому понедельнику
    days_to_subtract = today_weekday + 7
    # Находим дату прошлого понедельника
    last_monday = today - timedelta(days=days_to_subtract)
    # Создаём список из 7 дат, начиная с прошлого понедельника
    dates = []
    for i in range(7):
        current_date = last_monday + timedelta(days=i)
        dates.append(current_date.strftime('%d.%m.%Y'))

    return dates

# Составление списка дат для статистики мастеров за месяц
async def get_month_dates():
    # Получаем текущую дату
    today = datetime.now().date()
    # Для определения месяца вычисляем дату, которая была за указанное в конфиге дней назад.
    target_date = today - timedelta(days=config.LAST_MONTH_DAYS_AGO)
    # Определяем первый день целевого месяца
    first_day_of_month = target_date.replace(day=1)
    dates = []
    current_date = first_day_of_month

    # Цикл работает до тех пор, пока текущая дата меньше сегодняшней
    while current_date < today:
        # Проверяем, что дата относится к целевому месяцу
        if current_date.month == target_date.month:
            dates.append(current_date.strftime('%d.%m.%Y'))
        current_date += timedelta(days=1)
    return dates

# Определим ТО по пользователю или группе
async def get_to(message):
    # Получим ид пользователя и сравним со списком разрешенных в файле конфига
    user_id = message.from_user.id
    group_id = message.chat.id
    group_id *= -1
    t_o = False
    if user_id in config.USERS or group_id in config.GROUPS:
        # Приоритет группы потом юзеры? == да, для запросов другими начальниками
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
    return t_o

# Основная функция запуска бота
async def main():
    # Удаляем вебхук, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
