
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
        date_now = datetime.now()
        logger.info(f"Текущая дата: {date_now}")
        date_ago = date_now - timedelta(hours=config.HOUR)  # здесь мы выставляем минус 15 часов
        logger.info(f"Новая дата: {date_ago}")
        date_now_year = date_ago.strftime("%d.%m.%Y")
        date_now_no_year = date_ago.strftime("%d.%m")
        month_year = date_ago.strftime("%m.%Y")

        # Функция отправки отчета в телеграм по уже собранным данным
        if message.text.lower() == "привлеченные":
            # Для получения папки месяца привлеченных вычтем 8 дней(максимальный срок, когда они должны быть уже сданы)
            date_ago = date_ago - timedelta(8)
            date_now_year = date_ago.strftime("%d.%m.%Y")
            month_year = date_ago.strftime("%m.%Y")
        elif message.text.lower() == "неделя":
            # Обработка запроса "неделя"
            pass
        elif message.text.isdigit() and 1 <= int(message.text) <= config.MAX_REPORT_DAYS_AGO:
            days_to_subtract = int(message.text) - 1
            date_ago = date_ago - timedelta(days=days_to_subtract)
            logger.info(f"Новая дата: {date_ago}")
            date_now_year = date_ago.strftime("%d.%m.%Y")
            month_year = date_ago.strftime("%m.%Y")

        # # Для получения отчета только авторизованный админ
        # if user_id in config.USERS:

        # Парсер сообщений и сохранение в файл если это отчет.
        else:
            try:
                # Создадим папку за текущий день/месяц если не существует
                if not os.path.exists(f"files/{t_o}/{month_year}/{date_now_year}"):
                    os.makedirs(f"files/{t_o}/{month_year}/{date_now_year}")
                await parser_report(t_o, message)
            except IndexError:
                logger.info("Тут видимо сообщение не относящееся к отчету.")


async def parser_report(t_o, message):

    et_int = 0
    et_int_pri = 0
    et_tv = 0
    et_tv_pri = 0
    et_dom = 0
    et_dom_pri = 0
    et_serv = 0
    et_serv_tv = 0

    # Создадим флаги для поиска ошибок
    et_int_flag = 0
    et_int_pri_flag = 0
    et_tv_flag = 0
    et_tv_pri_flag = 0
    et_dom_flag = 0
    et_dom_pri_flag = 0
    et_serv_flag = 0
    et_serv_tv_flag = 0

    # TODO Разбивка по ":" старый способ, по нему определялся провайдер.
    # TODO Добавить проверку если будут проблемы
    # Разбиваем по ":", так мы определим что это отчет.
    pre_txt_lower = message.text.lower()
    logger.info(f"pre_txt_lower {pre_txt_lower}")
    # Мастера могут добавлять лишние ":" при перечислении.
    pre_txt = (pre_txt_lower.replace("тв:", "тв").
               replace("ис:", "ис").
               replace("нет:", "нет").
               replace("он:", "он"))
    logger.info(f"pre_txt {pre_txt}")
    txt = pre_txt.split(":")
    logger.info(f"txt {txt}")

    # Заменим скобки и перенос строки пробелами и разобьем на список
    new_txt = (txt[1].replace("(", " ").
                   replace(")", " ").
                   replace("\n", " ").
                   replace(",", " ").
                   replace(":", "").
                   replace(";", "").
                   replace("\xa0", " ").
                   replace(".", " "))
    new_txt_list_with_space = new_txt.split(" ")
    new_txt_list = [i for i in new_txt_list_with_space if i]

    for num, val in enumerate(new_txt_list):
        if val.lower() == "интернет" and new_txt_list[num - 1].lower() != "сервис":
            try:
                et_int = int(new_txt_list.pop(num + 1))  # Следующее значение после "интернет"
                if et_int < 100:  # Проверка на длину значения, защита от номера сервиса
                    et_int_flag = 1  # Флаг для проверки правильности отчета
            except ValueError:
                et_int = 0
            # logger.info(new_txt_list)

    # Сочетание тв
    for num, val in enumerate(new_txt_list):
        if val.lower() == "тв":
            if new_txt_list[num - 1].lower() == "сервис":
                try:
                    et_serv_tv = int(new_txt_list.pop(num + 1))  # После "тв"
                    if et_serv_tv < 100:  # Проверка на длину значения, защита от номера сервиса
                        et_serv_tv_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    et_serv_tv = 0
                except IndexError:  # После сервисов тв часто не ставят значение, а это конец сообщения
                    et_serv_tv = 0
                # logger.info(new_txt_list)

    for num, val in enumerate(new_txt_list):
        if val.lower() == "тв":
            if new_txt_list[num - 1].lower() != "сервис":
                try:
                    et_tv = int(new_txt_list.pop(num + 1))  # После "тв"
                    if et_tv < 100:  # Проверка на длину значения, защита от номера сервиса
                        et_tv_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    et_tv = 0
                except IndexError:  # После сервисов тв часто не ставят значение, а это конец сообщения
                    et_tv = 0
                # logger.info(new_txt_list)
    # Домофон
    for num, val in enumerate(new_txt_list):
        if val.lower() == "домофон":
            try:
                et_dom = int(new_txt_list.pop(num + 1))  # После "домофон"
                if et_dom < 100:  # Проверка на длину значения, защита от номера сервиса
                    et_dom_flag = 1  # Флаг для проверки правильности отчета
            except ValueError:
                et_dom = 0
            # logger.info(new_txt_list)

    # Сервис интернет
    for num, val in enumerate(new_txt_list):
        if val.lower() == "сервис" and new_txt_list[num + 1].lower() == "интернет":
            try:
                et_serv = int(new_txt_list.pop(num + 2))  # + 2 ибо через слово "интернет"
                if et_serv < 100:  # Проверка на длину значения, защита от номера сервиса
                    et_serv_flag = 1  # Флаг для проверки правильности отчета
            except ValueError:
                et_serv = 0
            # logger.info(new_txt_list)

    flag_priv_int = 0
    flag_priv_tv = 0
    flag_priv_dom = 0

    # Привлеченные
    for num, val in enumerate(new_txt_list):
        if val[0:4].lower() == "прив":
            if flag_priv_int == 0:  # Флаг привлеченного интернета
                # logger.info(f"тут привлеченный интернет {new_txt_list[num - 1]}")
                flag_priv_int += 1
                try:
                    et_int_pri = int(new_txt_list[num - 1])  # Перед "прив"
                    if et_int_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                        et_int_pri_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    et_int_pri = 0
            elif flag_priv_tv == 0:  # Флаг привлеченного тв
                # logger.info(f"тут привлеченный тв {new_txt_list[num - 1]}")
                flag_priv_tv += 1
                try:
                    et_tv_pri = int(new_txt_list[num - 1])  # Перед "прив"
                    if et_tv_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                        et_tv_pri_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    et_tv_pri = 0
            elif flag_priv_dom == 0:  # Флаг привлеченного домофона
                # logger.info(f"тут привлеченный домофон {new_txt_list[num - 1]}")
                flag_priv_dom += 1
                try:
                    et_dom_pri = int(new_txt_list[num - 1])  # Перед "прив"
                    if et_dom_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                        et_dom_pri_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    et_dom_pri = 0

    to_save = {
        "et_int": et_int,
        "et_int_pri": et_int_pri,
        "et_tv": et_tv,
        "et_tv_pri": et_tv_pri,
        "et_dom": et_dom,
        "et_dom_pri": et_dom_pri,
        "et_serv": et_serv,
        "et_serv_tv": et_serv_tv,
        'master': "не указан",
        'msg_err_txt': ""  # Запись текста с возможными ошибками
    }
    logger.info(f"Для сохранения: {to_save}")

    # Если в начале сообщения есть фамилия, то возьмем ее.
    txt_soname_pre = txt[0].replace("\n", " ")
    txt_soname = txt_soname_pre.split(" ")
    if txt_soname[0][0:2].lower() != 'ет':
        if txt_soname[0][0:2].lower() == "то":
            await message.reply("Необходимо указать фамилию мастера, отчет не сохранен.")
            return
        else:
            to_save["master"] = txt_soname[0].title()

    if to_save["master"] == "не указан":
        await message.reply("Необходимо указать фамилию мастера, отчет не сохранен.")
        return

    # Сообщение об ошибке на основе флагов
    msg_err = []
    if et_int_flag == 0:
        msg_err.append("ЕТ интернет. ")
    if et_int_pri_flag == 0:
        msg_err.append("ЕТ интернет. ")  # привлеченный
    if et_tv_flag == 0:
        msg_err.append("ЕТ тв. ")
    if et_tv_pri_flag == 0:
        msg_err.append("ЕТ тв. ")  # привлеченный
    if et_dom_flag == 0:
        msg_err.append("ЕТ домофон. ")
    if et_dom_pri_flag == 0:
        msg_err.append("ЕТ домофон. ")  # привлеченный
    if et_serv_flag == 0:
        msg_err.append("ЕТ сервис. ")
    if et_serv_tv_flag == 0:
        msg_err.append("ЕТ сервис тв. ")

    if len(msg_err) > 0:
        msg_err_txt = f""
        for e in msg_err:
            msg_err_txt += e
        await message.reply(f"Внимание, возможна ошибка с отчетом мастера "
                            f"{to_save['master']}: {msg_err_txt} Отчет не сохранен.")
        return

# Основная функция запуска бота
async def main():
    # Удаляем вебхук, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг
    logger.info("Бот запущен")
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
