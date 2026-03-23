import os
import json
import logging
from datetime import datetime, timedelta

# import pandas as pd
from aiogram import Bot
from aiogram.types import FSInputFile

import crud
import parser
import config
import to_exel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Исключение для ошибок валидации"""
    pass

# Парсера отчета из сообщения мастера
class ReportParser:
    def __init__(self, message, t_o, date_now_full, month_year):
        self.message = message  # Сообщение из ТГ
        self.main_txt = []      # Разобранное сообщения для обработки парсером
        self.t_o = t_o          # Территориальное подразделение
        self.date_now_full = date_now_full      # Обсчитанная дата с годом
        self.month_year = month_year            # Обсчитанная дата месяц/год для папок

        # Счетчик количества сделанных заявок
        self.et_int = 0
        self.et_int_pri = 0
        self.et_tv = 0
        self.et_tv_pri = 0
        self.et_dom = 0
        self.et_dom_pri = 0
        self.et_serv = 0
        self.et_serv_tv = 0
        # self.counters = {
        #     "et_int": 0, "et_int_pri": 0, "et_tv": 0,
        #     "et_tv_pri": 0, "et_dom": 0, "et_dom_pri": 0,
        #     "et_serv": 0, "et_serv_tv": 0
        # }

        # Флаги для поиска ошибок. 0 == ошибка.
        self.et_int_flag = 0
        self.et_int_pri_flag = 0
        self.et_tv_flag = 0
        self.et_tv_pri_flag = 0
        self.et_dom_flag = 0
        self.et_dom_pri_flag = 0
        self.et_serv_flag = 0
        self.et_serv_tv_flag = 0
        # self.flags = {
        #     "et_int": 0, "et_int_pri": 0, "et_tv": 0,
        #     "et_tv_pri": 0, "et_dom": 0, "et_dom_pri": 0,
        #     "et_serv": 0, "et_serv_tv": 0
        # }

        # Фамилия мастера для сохранения отчета
        self.master = "не указан"
        # Список указанных мастером номеров сервисных заявок(все кроме ЛС подключений)
        self.list_repairs = []

    # Запуск всех методов для обработки отчета
    async def process_report(self):
        try:
            await self._parse_message()     # Обработка сообщения, разделение по ":"
            await self._validate_date()     # Проверка наличия даты перед фамилией
            # !!! Вызов из функции обработки даты
            # await self._validate_master()   # Если не указана фамилия, обрабатывать дальше нет смысла
            await self._parse_report()      # Сбор количества выполненных заявок
            await self._validate_error()    # Обработка ошибок, отсутствия необходимых пунктов
            await self._collect_repair_numbers()        # Составление списка номеров сервисов
            await self._save_report_json()
            await self._save_report_db()
            await self._send_parsed_report_to_chat()    # Отправим обработанный отчет текстов в чат
        except ValueError as e:
            await self.message.reply(str(e))
            return
        except ValidationError as e:
            await self.message.reply(str(e))
            return

    # Обработка сообщения, разделение по ":"
    async def _parse_message(self):
        # TODO Разбивка по ":" старый способ, по нему определялся провайдер.
        # TODO Добавить проверку если будут проблемы
        # Разбиваем по ":", так мы определим что это отчет.
        pre_txt_lower = self.message.text.lower()
        # Мастера могут добавлять лишние ":" при перечислении.
        pre_txt = (pre_txt_lower.replace("тв:", "тв").
                   replace("ис:", "ис").
                   replace("нет:", "нет").
                   replace("он:", "он"))
        self.main_txt = pre_txt.split(":")

    # Проверка наличия даты перед фамилией
    async def _validate_date(self):
        # Берем первый элемент сообщения и удаляем лишние пробелы
        first_block = self.main_txt[0].strip()
        # Разбиваем первый блок по пробелу, чтобы отделить дату от текста
        first_element = first_block.split(" ")
        # Пытаемся преобразовать первый элемент в дату
        try:
            report_date = datetime.strptime(first_element[0].strip(), "%d.%m.%Y").date()

            # Если это дата, сохраняем её в двух форматах
            self.date_now_full = report_date.strftime("%d.%m.%Y")
            self.month_year = report_date.strftime("%m.%Y")

            # В случае успеха всех проверок(!) смотрим кто прислал отчет, с датой разрешено только админам
            user_id = self.message.from_user.id
            if user_id not in config.USERS:
                raise ValidationError('Отправка отчета с датой смертным запрещена. Отчёт не сохранён.')

            new_main_list = self.main_txt[0].split()
            print(f"new_main_list[1] {new_main_list[1]}")
            await self._validate_master(new_main_list[1])

        except ValueError:
            new_main_list = self.main_txt[0].split()
            await self._validate_master(new_main_list[0])

    # Определение мастера
    async def _validate_master(self, new_main_txt):
        # Если в начале сообщения есть фамилия, то возьмем ее.
        txt_soname_pre = new_main_txt.replace("\n", " ")
        # txt_soname_pre = self.main_txt[0].replace("\n", " ")
        txt_soname = txt_soname_pre.split(" ")
        # if txt_soname[0][0:2].lower() != 'ет':
        #     if txt_soname[0][0:2].lower() == "то":
        if txt_soname[0][0:2].lower() == 'ет' or txt_soname[0][0:2].lower() == "то":
            raise ValidationError('Необходимо указать фамилию мастера. Отчёт не сохранён.')
        elif txt_soname[0].lower() == "фамилия":
            raise ValidationError('Необходимо указать фамилию мастера, а не просто написать "фамилия". Отчёт не сохранён.')
        else:
            self.master = txt_soname[0].title()
        if self.master == "не указан" or self.master == "":
            raise ValidationError('Необходимо указать фамилию мастера. Отчёт не сохранён.')

    # Обработка отчета для получения количества выполненных заявок
    async def _parse_report(self):
        # Заменим скобки и перенос строки пробелами и разобьем на список
        new_txt = (self.main_txt[1].replace("(", " ").
                   replace(")", " ").
                   replace("\n", " ").
                   replace(",", " ").
                   replace(":", "").
                   replace(";", "").
                   replace("\xa0", " ").
                   replace(".", " "))
        new_txt_list_with_space = new_txt.split(" ")
        new_txt_list = [i for i in new_txt_list_with_space if i]

        # Интернет
        for num, val in enumerate(new_txt_list):
            if val.lower() == "интернет" and new_txt_list[num - 1].lower() != "сервис":
                try:
                    self.et_int = int(new_txt_list.pop(num + 1))  # Следующее значение после "интернет"
                    if self.et_int < 100:  # Проверка на длину значения, защита от номера сервиса
                        self.et_int_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    self.et_int = 0
                # logger.info(new_txt_list)

        # Сервис тв
        for num, val in enumerate(new_txt_list):
            if val.lower() == "тв":
                if new_txt_list[num - 1].lower() == "сервис":
                    try:
                        self.et_serv_tv = int(new_txt_list.pop(num + 1))  # После "тв"
                        if self.et_serv_tv < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_serv_tv_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_serv_tv = 0
                    except IndexError:  # После сервисов тв часто не ставят значение, а это конец сообщения
                        self.et_serv_tv = 0
                    # logger.info(new_txt_list)

        # ТВ
        for num, val in enumerate(new_txt_list):
            if val.lower() == "тв":
                if new_txt_list[num - 1].lower() != "сервис":
                    try:
                        self.et_tv = int(new_txt_list.pop(num + 1))  # После "тв"
                        if self.et_tv < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_tv_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_tv = 0
                    except IndexError:  # После сервисов тв часто не ставят значение, а это конец сообщения
                        self.et_tv = 0
                    # logger.info(new_txt_list)
        # Домофон
        for num, val in enumerate(new_txt_list):
            if val.lower() == "домофон":
                try:
                    self.et_dom = int(new_txt_list.pop(num + 1))  # После "домофон"
                    if self.et_dom < 100:  # Проверка на длину значения, защита от номера сервиса
                        self.et_dom_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    self.et_dom = 0
                # logger.info(new_txt_list)

        # Сервис интернет
        for num, val in enumerate(new_txt_list):
            if val.lower() == "сервис" and new_txt_list[num + 1].lower() == "интернет":
                try:
                    self.et_serv = int(new_txt_list.pop(num + 2))  # + 2 ибо через слово "интернет"
                    if self.et_serv < 100:  # Проверка на длину значения, защита от номера сервиса
                        self.et_serv_flag = 1  # Флаг для проверки правильности отчета
                except ValueError:
                    self.et_serv = 0

        # Вычисление привлеченных, а так же поиск ошибки отсутствия нужного количества слов "прив" в отчете.
        # Перебор отчета, первый привлеченный идет в интернет, второй в тв, третий в домофон.
        # Флаги для правильности перебора
        flag_priv_int = 0
        flag_priv_tv = 0
        flag_priv_dom = 0
        for num, val in enumerate(new_txt_list):
            if val[0:4].lower() == "прив":
                if flag_priv_int == 0:  # Флаг привлеченного интернета
                    flag_priv_int = 1
                    try:
                        self.et_int_pri = int(new_txt_list[num - 1])  # Перед "прив"
                        if self.et_int_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_int_pri_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_int_pri = 0
                elif flag_priv_tv == 0:  # Флаг привлеченного тв
                    flag_priv_tv = 1
                    try:
                        self.et_tv_pri = int(new_txt_list[num - 1])  # Перед "прив"
                        if self.et_tv_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_tv_pri_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_tv_pri = 0
                elif flag_priv_dom == 0:  # Флаг привлеченного домофона
                    flag_priv_dom = 1
                    try:
                        self.et_dom_pri = int(new_txt_list[num - 1])  # Перед "прив"
                        if self.et_dom_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_dom_pri_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_dom_pri = 0

    # Обработка ошибок, отсутствия необходимых пунктов
    async def _validate_error(self):
        # Сообщение об ошибке на основе флагов
        msg_err = []
        if self.et_int_flag == 0:
            msg_err.append("ЕТ интернет. ")
        if self.et_int_pri_flag == 0:
            msg_err.append("ЕТ привлеченный интернет. ")  # привлеченный
        if self.et_tv_flag == 0:
            msg_err.append("ЕТ тв. ")
        if self.et_tv_pri_flag == 0:
            msg_err.append("ЕТ привлеченный тв. ")  # привлеченный
        if self.et_dom_flag == 0:
            msg_err.append("ЕТ домофон. ")
        if self.et_dom_pri_flag == 0:
            msg_err.append("ЕТ привлеченный домофон. ")  # привлеченный
        if self.et_serv_flag == 0:
            msg_err.append("ЕТ сервис. ")
        if self.et_serv_tv_flag == 0:
            msg_err.append("ЕТ сервис тв. ")

        if len(msg_err) > 0:
            msg_err_txt = f""
            for e in msg_err:
                msg_err_txt += e
            raise ValidationError(f"Внимание, возможна ошибка с отчетом мастера "
                                     f"{self.master}: {msg_err_txt} Отчет не сохранен.")

    # Составление списка номеров сервисов
    async def _collect_repair_numbers(self):
        # Заменяем символы, чтобы номера сервисов гарантированно окружались пробелами
        repairs_txt_et = (self.main_txt[1].replace("(", " ").
                          replace(")", " ").
                          replace("\n", " ").
                          replace("#", " ").
                          replace("e", " ").  # Английская. Тут мастера могут записать етм
                          replace("е", " ").  # Русская

                          # Для обозначения актовых и без актовых
                          replace("a", " ").  # Английская
                          replace("а", " ").  # Русская
                          replace("б", " ").  # Русская
                          replace("t", " ").  # Английская
                          replace("т", " ").  # Русская

                          replace(";", " ").
                          replace("-", " ").
                          replace(",", " ").
                          replace("\xa0", " ").
                          replace(".", " "))

        repairs_txt_et_list = repairs_txt_et.split(" ")

        # Добавляем в список все 7-ми значные номера
        for i in repairs_txt_et_list:
            if len(i) == 7 and i.isnumeric():
                self.list_repairs.append(['ЕТ', i, self.master])

    # Сохранение отчета в json
    async def _save_report_json(self):
        # Создадим папку за текущий день/месяц если не существует
        if not os.path.exists(f"files/{self.t_o}/{self.month_year}/{self.date_now_full}"):
            os.makedirs(f"files/{self.t_o}/{self.month_year}/{self.date_now_full}")

        # data = {**self.counters, "master": self.master, "list_repairs": self.list_repairs}
        data = {
            "et_int": self.et_int,
            "et_int_pri": self.et_int_pri,
            "et_tv": self.et_tv,
            "et_tv_pri": self.et_tv_pri,
            "et_dom": self.et_dom,
            "et_dom_pri": self.et_dom_pri,
            "et_serv": self.et_serv,
            "et_serv_tv": self.et_serv_tv,

            "master": self.master,
            "list_repairs": self.list_repairs
        }
        with open(f'files/{self.t_o}/{self.month_year}/{self.date_now_full}/{self.master}.json', 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    # Сохранение отчета в бд
    async def _save_report_db(self):
        report = {
            "et_int": self.et_int,
            "et_int_pri": self.et_int_pri,
            "et_tv": self.et_tv,
            "et_tv_pri": self.et_tv_pri,
            "et_dom": self.et_dom,
            "et_dom_pri": self.et_dom_pri,
            "et_serv": self.et_serv,
            "et_serv_tv": self.et_serv_tv,
        }
        crud.add_master_day_report(master=self.master, t_o=self.t_o, report=report,
                                   data_month=self.month_year, date_full=self.date_now_full,
                                   task_list=self.list_repairs)

    # Отправим обработанный отчет текстов в чат
    async def _send_parsed_report_to_chat(self):
        answer = (f"{self.t_o} {self.date_now_full}. Мастер {self.master} \n\n"
                  f"Интернет {self.et_int}"
                  f"({self.et_int_pri}), "
                  f"ТВ {self.et_tv}({self.et_tv_pri}), "
                  f"домофон {self.et_dom}({self.et_dom_pri}), "
                  f"сервис {self.et_serv}, "
                  f"сервис ТВ {self.et_serv_tv}")
        await self.message.answer(answer)

# Извлечение привлеченных из сообщения мастера
class PaserPriv:
    def __init__(self, message, t_o, date_now_full, month_year):
        ...

# Вывод отчета за день
class ReportCalc:
    def __init__(self, message, t_o, files, date_month_year, report_folder):
        self.bot = message.bot
        self.message = message              # Сообщение из ТГ
        self.t_o = t_o                      # Территориальное отделение
        self.files = files                  # Список с файлами в папке с отчетами за день
        self.date_month_year = date_month_year  # Имя папки(месяц/год) с отчетами за месяц
        self.date_full = report_folder      # Имя папки(день/месяц/год) с отчетами за день

        self.num_rep = 0        # Количество отчетов для сверки.
        self.list_masters = []  # Список мастеров в отчете, для сверки.
        self.parser_answer = [] # Ответ парсера адресов по номерам

        self.to_save = {
            "et_int": 0,
            "et_int_pri": 0,
            "et_tv": 0,
            "et_tv_pri": 0,
            "et_dom": 0,
            "et_dom_pri": 0,
            "et_serv": 0,
            "et_serv_tv": 0,
            "list_repairs": [],
        }

    # Запуск всех методов для обработки обсчета ответов
    async def process_report(self):
        # Основной сбор данных и базовая отчётность
        await self._read_jsons()            # Чтение файлов json в папке
        await self._send_answer_to_chat()   # Отправка ответа со списком мастеров в чат
        await self._send_calc_report_to_chat()   # Отправка общего количество выполненных заявок в чат
        await self._save_report_json()      # Сохраним в json общее количество выполненных задач и все их номера
        await self._save_report_db()        # Сохраним в db счетчик задач, номера сервисов не сохраняем
        # Дополнительная обработка заявок
        await self._parser_address()        # Получим адреса и типы всех задач
        await self._save_report_exel()      # Сохраним результат парсера в ексель
        await self._send_exel_to_chat()     # Отправим ексель файл в чат тг
        # Аналитика
        if await self._check_day_report_all_to():  # Проверка все ли ТО сделали дневной отчет
            stat = await self._average_day_statistics()     # Подсчет средней статистики
            await self._send_average_day_statistic_to_chat(stat)  # Отправка статистики по чатам

    # Чтение файлов с отчетами за день. Извлечение количества выполненных заявок и списка номеров заданий.
    async def _read_jsons(self):
        for file in self.files:
            if file[-4:] == "json":
                with open(f'files/{self.t_o}/{self.date_month_year}/{self.date_full}/{file}', 'r', encoding='utf-8') as outfile:
                    data = json.loads(outfile.read())
                    self.to_save["et_int"] += data["et_int"]
                    self.to_save["et_int_pri"] += data["et_int_pri"]
                    self.to_save["et_tv"] += data["et_tv"]
                    self.to_save["et_tv_pri"] += data["et_tv_pri"]
                    self.to_save["et_dom"] += data["et_dom"]
                    self.to_save["et_dom_pri"] += data["et_dom_pri"]
                    self.to_save["et_serv"] += data["et_serv"]
                    self.to_save["et_serv_tv"] += data["et_serv_tv"]
                    self.to_save["list_repairs"] += data["list_repairs"] # Сложим же все номера заданий

                    self.num_rep += 1  # Добавим счетчик количества посчитанных
                    self.list_masters.append(data["master"])  # Добавим фамилию мастера

    # Отправим список полученных отчетов в чат
    async def _send_answer_to_chat(self):
        # Выведем имена мастеров для сверки
        answer = "Получены отчеты: \n"
        for master in self.list_masters:
            answer += f'{master} \n'
        await self.message.answer(answer)

    # Отправим общее количество выполненных заявок в чат
    async def _send_calc_report_to_chat(self):
        answer = (f"{self.t_o} {self.date_full} \n\n"
                  f"Интернет {self.to_save["et_int"]}"
                  f"({self.to_save["et_int_pri"]}), "
                  f"ТВ {self.to_save["et_tv"]}({self.to_save["et_tv_pri"]}), "
                  f"домофон {self.to_save["et_dom"]}({self.to_save["et_dom_pri"]}), "
                  f"сервис {self.to_save["et_serv"]}, "
                  f"сервис ТВ {self.to_save["et_serv_tv"]}")
        await self.message.answer(answer)

    # Сохранение дневного отчета то в БД
    async def _save_report_db(self):
        crud.add_full_day_report(t_o=self.t_o, report=self.to_save, data_month=self.date_month_year,
                                   date_full=self.date_full)

    # Сохранение дневного отчета то в json
    async def _save_report_json(self):
        # Сохраним в json файл итоговый результат
        with open(f'files/{self.t_o}/{self.date_month_year}/{self.date_full}.json', 'w') as outfile:
            json.dump(self.to_save, outfile, sort_keys=False, ensure_ascii=False, indent=4, separators=(',', ': '))

    # Получение адресов по списку номеров заданий
    async def _parser_address(self):
        # Получим обработанный список из парсера
        self.parser_answer = await parser.get_address(self.to_save["list_repairs"])

    # Сохранение отчета в exel
    async def _save_report_exel(self):
        # Сохраним ексель файл с номерами ремонтов
        await to_exel.save_to_exel(list_to_exel=self.parser_answer, t_o=self.t_o,
                                   full_date=self.date_full, date_month_year=self.date_month_year)

    # Отправка exel файла в чат
    async def _send_exel_to_chat(self):
        file = FSInputFile(f"files/{self.t_o}/{self.date_month_year}/{self.date_full}.xls",
                           filename=f"{self.date_full}.xls")
        await self.message.answer_document(file)

    # Проверка все ли ТО сделали дневной отчет.
    # Для дальнейшего вычисления средней статистики по всем ТО.
    async def _check_day_report_all_to(self):
        return crud.check_all_full_day_report(date_full=self.date_full)

    # Подсчет средней дневной статистики по всем ТО.
    async def _average_day_statistics(self):
        stats = crud.get_average_day_statistic_for_all_to(date_full=self.date_full)
        return stats

    # Отправим среднюю статистику выполненных заявок в чат
    async def _send_average_day_statistic_to_chat(self, stats):
        if not stats:
            answer = "Не удалось получить дневную статистику по подразделениям. 😔"
            await self.message.answer(answer)
            return

        # Формируем сообщение для бота
        lines = [f"**📊 Дневная статистика по подразделениям за {self.date_full}:**\n"]
        for t_o, master_count, total_requests, average_requests in stats:
            line = (f"**Подразделение:** {t_o}\n"
                    f"**Количество мастеров:** {master_count}\n"
                    f"**Всего заявок:** {total_requests}\n"
                    f"**В среднем на мастера:** {average_requests:.2f}\n")
            lines.append(line)

        answer = "\n---\n".join(lines)
        # await self.message.answer(answer, parse_mode="Markdown")
        for group_id in config.CHAT_FOR_DAY_STATISTIC:
            try:
                await self.bot.send_message(chat_id=group_id, text=answer, parse_mode="Markdown")
                logger.info(f"Сообщение успешно отправлено в чат {group_id}")
            except Exception as e:
                logger.info(f"Не удалось отправить сообщение в чат {group_id}: {e}")

# Сбор недельной статистики
class ReportWeek:
    def __init__(self, message, t_o, week):
        self.message = message              # Сообщение из ТГ
        self.t_o = t_o                      # Территориальное отделение
        self.week = week                    # 7 дат прошлой недели
        self.to_save = {
            "et_int": 0,
            "et_int_pri": 0,
            "et_tv": 0,
            "et_tv_pri": 0,
            "et_dom": 0,
            "et_dom_pri": 0,
            "et_serv": 0,
            "et_serv_tv": 0,
        }

    # Запуск всех методов для обработки обсчета статистики
    async def process_report(self):
        await self._get_days()              # Перебор дней недели
        await self._send_answer_to_chat()   # Отправка ответа в тг

    # Перебор дней недели
    async def _get_days(self):
        for day in self.week:
            day_reports = crud.get_reports_for_day(date_full=day, t_o=self.t_o)
            await self._calc_day(day_reports)

    # Сложим все отчеты в рамках одного дня
    async def _calc_day(self, day_reports):
        for report in day_reports:
            self.to_save["et_int"] += report["et_int"]
            self.to_save["et_int_pri"] += report["et_int_pri"]
            self.to_save["et_tv"] += report["et_tv"]
            self.to_save["et_tv_pri"] += report["et_tv_pri"]
            self.to_save["et_dom"] += report["et_dom"]
            self.to_save["et_dom_pri"] += report["et_dom_pri"]
            self.to_save["et_serv"] += report["et_serv"]
            self.to_save["et_serv_tv"] += report["et_serv_tv"]

    # Отправка ответа в тг
    async def _send_answer_to_chat(self):
        answer = (f"Статистика за: {self.week[0]} - {self.week[-1]} \n\n"
                  f"Выполнено: \n"
                  f"Интернет {self.to_save["et_int"]} "
                  f"({self.to_save["et_int_pri"]}), \n"
                  f"ТВ {self.to_save["et_tv"]}({self.to_save["et_tv_pri"]}), \n"
                  f"домофон {self.to_save["et_dom"]}({self.to_save["et_dom_pri"]}), \n"
                  f"сервис {self.to_save["et_serv"]}, \n"
                  f"сервис ТВ {self.to_save["et_serv_tv"]}")
        await self.message.answer(answer)

# Вывода статистики по всем мастерам в то
class MastersStatistic:
    def __init__(self, message, t_o, month):
        self.message = message              # Сообщение из ТГ, необходимо для целевого ответа
        self.t_o = t_o                      # Территориальное отделение
        self.month = month          # Даты нужного месяца
        # self.date_month_year = ""   # Имя папки(месяц/год) с отчетами за месяц
        self.masters = {}

    # Запуск всех методов для обработки обсчета статистики
    async def process_report(self):
        await self._get_days()              # Перебор дней месяца
        # Далее по цепочке обрабатываются для каждого дня: _read_db() => _read_day()
        await self._calc_salary()           # Подсчет предполагаемой зарплаты
        await self._send_answer_to_chat()   # Отправка ответа в тг

    # Перебор дней месяца
    async def _get_days(self):
        for day in self.month:
            await self._read_db(day)

    # Получение одного дня из бд
    async def _read_db(self, day):
        for t_o in self.t_o:
            day_reports = crud.get_reports_for_day(date_full=day, t_o=t_o)
            for report in day_reports:
                await self._read_day(report=report)

    # Обработка одного дня
    async def _read_day(self, report):
        master = report["master"]
        if master not in self.masters:
            self.masters[master] = {
                "et_int": 0,
                "et_int_pri": 0,
                "et_tv": 0,
                "et_tv_pri": 0,
                "et_dom": 0,
                "et_dom_pri": 0,
                "et_serv": 0,
                "et_serv_tv": 0,
                "all_tasks": 0,
                "install_internet": 0,
                "other_tasks": 0,
                "days": 0,
            }
        self.masters[master]["et_int"] += report["et_int"]
        self.masters[master]["et_int_pri"] += report["et_int_pri"]
        self.masters[master]["et_tv"] += report["et_tv"]
        self.masters[master]["et_tv_pri"] += report["et_tv_pri"]
        self.masters[master]["et_dom"] += report["et_dom"]
        self.masters[master]["et_dom_pri"] += report["et_dom_pri"]
        self.masters[master]["et_serv"] += report["et_serv"]
        self.masters[master]["et_serv_tv"] += report["et_serv_tv"]
        self.masters[master]["all_tasks"] += report["et_int"] + report["et_tv"] + report["et_dom"] + report["et_serv"] + \
                                             report["et_serv_tv"]
        self.masters[master]["install_internet"] += report["et_int"]
        self.masters[master]["other_tasks"] += report["et_tv"] + report["et_dom"] + report["et_serv"] + report["et_serv_tv"]
        self.masters[master]["days"] += 1

    # Подсчет предполагаемой зарплаты по очень средним параметрам
    async def _calc_salary(self):
        for master_name, master_data in self.masters.items():
            master_data["salary"] = 0
            avr_int_num = master_data["install_internet"] / master_data["days"]
            avr_oth_task = master_data["other_tasks"] / master_data["days"]
            if master_data["days"] > 15: # Если есть доп смены посчитаем от среднего
                master_data["salary"] = 15 * (avr_int_num * 1250) + 15 * (avr_oth_task * 1000)
                master_data["salary"] += (master_data["days"] - 15) * (avr_int_num * 1670)     # Доп дни
                master_data["salary"] += (master_data["days"] - 15) * (avr_oth_task * 1670)    # Доп дни
            else:   # Если нет дополнительных смен, считаем от фактического, а не от среднего
                master_data["salary"] = master_data["install_internet"] * 1250
                master_data["salary"] += master_data["other_tasks"] * 1000

    # Отправка ответа в тг
    async def _send_answer_to_chat(self):
        sorted_list = sorted(
            [
                (name, data)
                for name, data in self.masters.items()
                if data["all_tasks"] > 5
            ],
            key=lambda item: item[1]["all_tasks"],
            reverse=True,
        )
        for master_name, master_data in sorted_list:
            answer = (f"{master_name} \n\n"
                      # f"Выполнено: \n"
                      f"Интернет {master_data["et_int"]} "
                      f"({master_data["et_int_pri"]}), \n"
                      f"ТВ {master_data["et_tv"]}({master_data["et_tv_pri"]}), \n"
                      f"Домофон {master_data["et_dom"]}({master_data["et_dom_pri"]}), \n"
                      f"Сервис {master_data["et_serv"]}, \n"
                      f"Сервис ТВ {master_data["et_serv_tv"]} \n\n"
                      f"Всего выполнено: {master_data["all_tasks"]} \n"
                      f"Отработано смен: {master_data["days"]} \n"
                      f"Среднее за смену: {round(master_data["all_tasks"]/master_data["days"], 1)} \n"
                      f"...: {round(master_data["salary"])} \n"
                      )

            await self.message.answer(answer)

# Вывода статистики одного мастера по всем то
class OneMasterStatistic:
    # --- КОНСТАНТЫ ОПЛАТЫ ---
    COEFFS = {
        'workday': {
            'install_internet': 1250,  # Установка интернета, рабочий день
            'other_tasks': 1000,  # Прочие работы, рабочий день
        },
        'weekend': {
            'install_internet': 1670,  # Установка интернета, выходной день
            'other_tasks': 1670,  # Прочие работы, выходной день
        }
    }
    def __init__(self, message, master_soname: str, month: list[str]):
        self.message = message              # Сообщение из ТГ
        self.master_soname = master_soname  # Фамилия мастера для поиска в БД.
        self.month = month                  # Даты нужного месяца. Список строк.

        self.master_tasks = {
            "et_int": 0,
            "et_int_pri": 0,
            "et_tv": 0,
            "et_tv_pri": 0,
            "et_dom": 0,
            "et_dom_pri": 0,
            "et_serv": 0,
            "et_serv_tv": 0,
            "all_tasks": 0,
            "days": 0,
        }

        self.master = {
            "t_o": None,
            "schedule_day": None,          # График мастера, даты.
            "schedule_cycle": None,        # График мастера, цикл: 2/2, 3/3
            "master_soname": master_soname,
            "schedule_start_day": None,    # Начало графика
            # "schedule_start_date": pd.to_datetime('2025-09-15'),  # Начало графика
            "daily_reports": {},  # Словарь для хранения данных по дням: {дата: {работа_1: X, работа_2: Y, ...}}
            # Количество выходных и рабочих. Для сверки.
            "workday": 0,
            "weekend": 0,
        }

        self.total_earnings = 0

    # Запуск всех методов для обработки обсчета статистики
    async def process_report(self):
        await self._get_master_from_db()    # Получим мастера из БД(нужен его график)
        await self._get_days()              # Получаем данные о выполненных работах за месяц

        # Подсчет ЗП только для мастеров с графиком
        if self.master["schedule_cycle"]:
            await self._get_schedule()              # Создадим цикл графика мастера ([1, 1, 0, 0....]).
            await self._generate_full_schedule()    # Генерируем полный календарь (дата -> 'workday'/'weekend')
            await self._calculate_earnings()        # Считаем заработок, используя данные о работе и графике

        await self._send_answer_to_chat()   # Отправка ответа в тг


    async def _get_master_from_db(self):
        master = crud.get_master(soname=self.master_soname)
        if master:
            self.master["t_o"] = master[0]["t_o"]

            self.master["schedule_cycle"] = master[0]["schedule"]
            self.master["schedule_start_day"] = master[0]["schedule_start_day"]


    async def _generate_full_schedule(self):
        """
        Генерирует словарь 'Дата: Статус' (Статус: 'workday' или 'weekend')
        на основе schedule_list и start_day, покрывая все нужные дни месяца.
        """
        start_date_str = self.master["schedule_start_day"]
        pattern = self.schedule_list

        if not pattern or not start_date_str:
            print("Ошибка: График или стартовая дата не определены.")
            return

        # start_date = datetime.strptime(start_date_str, '%d-%m-%Y')
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')

        # Находим самую позднюю дату в месяце, чтобы сгенерировать график с запасом
        if self.month:
            all_dates = [datetime.strptime(d, '%d.%m.%Y') for d in self.month]
            end_date = max(all_dates)
        else:
            end_date = start_date

        # Определяем количество дней для генерации (с запасом)
        num_days = (end_date - start_date).days + len(pattern) + 1
        print(f"num_days{num_days}")

        full_schedule = {}
        current_date = start_date

        for i in range(num_days):
            # Используем оператор % для циклического повторения графика
            status_int = pattern[i % len(pattern)]

            # 1 - рабочий день ('workday'), 0 - выходной ('weekend')
            status = 'workday' if status_int == 1 else 'weekend'
            # if status_int == 1:
            #     status = 'workday'
            #     self.master["workday"] += 1
            # else:
            #     status = 'weekend'
            #     self.master["weekend"] += 1

            date_str = current_date.strftime('%d.%m.%Y')
            full_schedule[date_str] = status

            current_date += timedelta(days=1)

        self.full_schedule = full_schedule
        print(full_schedule)

    async def _calculate_earnings(self):
        """
        Рассчитывает общую сумму заработка на основе выполненной работы
        (daily_reports) и статуса дня (full_schedule).
        """
        total_earnings = 0

        # Итерируемся только по дням, в которые была выполнена работа
        for date_str, work_data in self.master["daily_reports"].items():
            # 1. Определяем статус дня по графику
            # Используем get() с дефолтом, хотя _generate_full_schedule
            # должен покрыть все даты месяца.
            day_status = self.full_schedule.get(date_str, 'weekend')

            # Подсчет отработанных дней
            if day_status == 'workday':
                self.master["workday"] += 1
            elif day_status == 'weekend':
                self.master["weekend"] += 1

            # 2. Выбираем соответствующие коэффициенты
            coeffs = self.COEFFS[day_status]

            # 3. Количество выполненных работ
            internet_installs = work_data.get('install_internet', 0)
            other_tasks = work_data.get('other_tasks', 0)

            # 4. Расчет оплаты за день (работа * коэффициент)
            daily_earning_int = internet_installs * coeffs['install_internet']
            daily_earning_other = other_tasks * coeffs['other_tasks']
            daily_total = daily_earning_int + daily_earning_other

            # 5. Добавляем к общей сумме
            total_earnings += daily_total

        self.total_earnings = total_earnings

        print(f"Общий заработок мастера {self.master_soname}: {self.total_earnings}")

    # Перебор дней месяца
    async def _get_days(self):
        for day in self.month:
            await self._read_db(day)
        print(self.master["daily_reports"])

    # Получение одного дня из бд
    async def _read_db(self, day):
        day_reports = crud.get_one_master_report_for_day(master=self.master_soname, date_full=day)
        for report in day_reports:
            await self._read_day(report=report, day=day)

    # Обработка одного дня
    async def _read_day(self, report, day):
        # Добавим к общему счетчику
        self.master_tasks["et_int"] += report["et_int"]
        self.master_tasks["et_int_pri"] += report["et_int_pri"]
        self.master_tasks["et_tv"] += report["et_tv"]
        self.master_tasks["et_tv_pri"] += report["et_tv_pri"]
        self.master_tasks["et_dom"] += report["et_dom"]
        self.master_tasks["et_dom_pri"] += report["et_dom_pri"]
        self.master_tasks["et_serv"] += report["et_serv"]
        self.master_tasks["et_serv_tv"] += report["et_serv_tv"]
        self.master_tasks["all_tasks"] += report["et_int"] + report["et_tv"] + report["et_dom"] + report["et_serv"] + \
                                             report["et_serv_tv"]
        self.master_tasks["days"] += 1

        # Подсчет ЗП только для мастеров с графиком
        if self.master["schedule_cycle"]:
            install_internet = report["et_int"]
            other_tasks = report["et_tv"] + report["et_dom"] + report["et_serv"] + report["et_serv_tv"]

            # Добавим в словарь, где ключ это дата.
            if day not in self.master["daily_reports"]:
                self.master["daily_reports"][day] = {
                    "install_internet": 0,
                    "other_tasks": 0,
                }
                self.master["daily_reports"][day]["install_internet"] = install_internet
                self.master["daily_reports"][day]["other_tasks"] = other_tasks

    async def _get_schedule(self):
        cycle_str = self.master["schedule_cycle"]
        # 1. Преобразуем строку в список чисел: [2, 2, 3, 2, 2, 3]
        cycle_parts = [int(p) for p in cycle_str.split('/')]

        self.schedule_list = []  # Очистим или инициализируем список перед использованием

        # Итерируемся по ЧЕТНЫМ индексам (0, 2, 4...)
        for i in range(0, len(cycle_parts), 2):

            # Рабочие дни (элементы с ЧЕТНЫМ индексом)
            # Пример: cycle_parts[0]=2, cycle_parts[2]=3, cycle_parts[4]=2
            self.schedule_list.extend([1] * cycle_parts[i])

            # Выходные дни (элементы с НЕЧЕТНЫМ индексом)
            # Проверяем, существует ли следующий (нечетный) элемент
            if i + 1 < len(cycle_parts):
                # Пример: cycle_parts[1]=2, cycle_parts[3]=2, cycle_parts[5]=3
                self.schedule_list.extend([0] * cycle_parts[i + 1])

        # print(self.schedule_list)

    # Отправка ответа в тг
    async def _send_answer_to_chat(self):
        if self.master_tasks["days"] > 0:
            answer = (f"{self.master_soname} \n\n"
                      # f"Выполнено: \n"
                      f"Интернет {self.master_tasks["et_int"]} "
                      f"({self.master_tasks["et_int_pri"]}), \n"
                      f"ТВ {self.master_tasks["et_tv"]}({self.master_tasks["et_tv_pri"]}), \n"
                      f"Домофон {self.master_tasks["et_dom"]}({self.master_tasks["et_dom_pri"]}), \n"
                      f"Сервис {self.master_tasks["et_serv"]}, \n"
                      f"Сервис ТВ {self.master_tasks["et_serv_tv"]} \n\n"
                      f"Всего выполнено: {self.master_tasks["all_tasks"]} \n"
                      f"Отработано смен: {self.master_tasks["days"]} \n"
                      f"Среднее за смену: {round(self.master_tasks["all_tasks"] / self.master_tasks["days"], 1)} \n\n"
                      )

            # Вывод ЗП только для мастеров с графиком
            if self.master["schedule_cycle"]:
                answer += (f"График мастера: {self.master["schedule_cycle"]} от {self.master["schedule_start_day"]}\n"
                           f"Отработано в выходные дни: {self.master["weekend"]}\n"
                           f"...: {self.total_earnings}"
                           )

            await self.message.answer(answer)
        else:
            await self.message.answer(f"Мастер не обнаружен!!!")

    # async def _get_reports_for_month(self):
    #     """Получает отчеты из БД для каждого дня текущего месяца."""
    #     if not self.master["t_o"]:
    #         return
    #
    #     print(f"📖 Чтение отчетов за {self.month[0][:7]}...")
    #     for day_str in self.month:
    #         # Преобразование строки обратно в дату для _read_day
    #         day_date = datetime.strptime(day_str, '%Y-%m-%d').date()
    #         await self._read_db(day_date)

    #
    # async def _read_db(self, day):
    #     """Получение одного дня из бд."""
    #     day_str = day.strftime('%Y-%m-%d')
    #     day_reports = crud.get_reports_for_day(date_full=day_str, t_o=self.master["t_o"])
    #
    #     for report in day_reports:
    #         # Передаем дату вместе с отчетом
    #         await self._read_day(report=report, day=day)
    #
    # async def _read_day(self, report: Dict[str, Any], day: dt.date):
    #     """Обработка одного дня, сохранение данных в daily_reports."""
    #     master_name = report["master"]
    #
    #     if master_name != self.master["name"]:
    #         return
    #
    #     day_key = day
    #
    #     if day_key not in self.master["daily_reports"]:
    #         self.master["daily_reports"][day_key] = {
    #             "install_internet": 0,
    #             "other_tasks": 0,
    #         }
    #
    #     install_internet = report.get("et_int", 0)
    #     other_tasks = (report.get("et_tv", 0) + report.get("et_dom", 0) +
    #                    report.get("et_serv", 0) + report.get("et_serv_tv", 0))
    #
    #     self.master["daily_reports"][day_key]["install_internet"] += install_internet
    #     self.master["daily_reports"][day_key]["other_tasks"] += other_tasks
    #

    #
    # async def _calculate_schedule(self, month_start: pd.Timestamp) -> dict:
    #     """Генерирует расписание (дата -> статус дня) для текущего месяца."""
    #
    #     cycle_str = self.master["schedule_cycle"]
    #     start_date = self.master["schedule_start_date"]
    #
    #     # Преобразование цикла
    #     cycle_parts = [int(p) for p in cycle_str.split('/')]
    #     schedule_list = []
    #     for i in range(0, len(cycle_parts), 2):
    #         schedule_list.extend([1] * cycle_parts[i])  # Рабочие
    #         if i + 1 < len(cycle_parts):
    #             schedule_list.extend([0] * cycle_parts[i + 1])  # Выходные
    #
    #     cycle_length = len(schedule_list)
    #
    #     # Генерация дат месяца
    #     month_end = month_start + pd.offsets.MonthEnd(0)
    #     current_month_dates = pd.date_range(month_start, month_end, freq='D')
    #
    #     # Расчет смещения
    #     days_passed = (month_start.normalize() - start_date.normalize()).days
    #     offset = days_passed % cycle_length
    #
    #     # Применение сдвига
    #     full_cycle = schedule_list * (len(current_month_dates) // cycle_length + 2)  # С запасом
    #     monthly_schedule = full_cycle[offset: offset + len(current_month_dates)]
    #
    #     # Формирование словаря: {дата: статус_дня}
    #     schedule_map = {}
    #     for date, status in zip(current_month_dates, monthly_schedule):
    #         schedule_map[date.date()] = status
    #
    #     return schedule_map
    #
    #
    #
    #
    # async def _read_day(self, report: dict, day: pd.Timestamp):
    #     """Обработка одного дня, сохранение данных в daily_reports."""
    #     master_name = report["master"]
    #
    #     # Проверяем, что это отчет нашего мастера
    #     if master_name != self.master["name"]:
    #         return
    #
    #     day_key = day.normalize().date()  # Используем дату как ключ (без времени)
    #
    #     if day_key not in self.master["daily_reports"]:
    #         self.master["daily_reports"][day_key] = {
    #             "install_internet": 0,
    #             "other_tasks": 0,
    #         }
    #
    #
    #     # Сохраняем только те данные, которые нужны для расчета ЗП.
    #     # Суммируем работы за этот день.
    #     install_internet = report["et_int"]
    #     other_tasks = report["et_tv"] + report["et_dom"] + report["et_serv"] + report["et_serv_tv"]
    #
    #     self.master["daily_reports"][day_key]["install_internet"] += install_internet
    #     self.master["daily_reports"][day_key]["other_tasks"] += other_tasks
    #
    # async def _calc_salary(self, month_start: pd.Timestamp):
    #     """Подсчет зарплаты по графику."""
    #
    #     # 1. Задаем коэффициенты для вашего графика
    #     # Используем новые, упрощенные коэффициенты, т.к. нет логики >15 дней
    #     # Здесь можно настроить разные ставки для рабочих и выходных дней
    #     COEFF_INT_WORKDAY = 1250  # Установка интернета, рабочий день
    #     COEFF_OTHER_WORKDAY = 1000  # Прочие работы, рабочий день
    #     COEFF_INT_WEEKEND = 1670  # Установка интернета, выходной день
    #     COEFF_OTHER_WEEKEND = 1670  # Прочие работы, выходной день
    #
    #     # 2. Генерируем расписание для месяца
    #     schedule_map = self._calculate_schedule(month_start)
    #
    #     total_salary = 0
    #
    #     # 3. Перебираем все дни, за которые были отчеты
    #     for day_date, report_data in self.master["daily_reports"].items():
    #
    #         # Получаем статус дня: 1 - рабочий, 0 - выходной
    #         day_status = schedule_map.get(day_date, -1)  # -1, если день не в текущем расчете
    #
    #         if day_status == -1:
    #             # Пропускаем дни, которые не входят в текущий месяц расчета
    #             continue
    #
    #         install_internet = report_data["install_internet"]
    #         other_tasks = report_data["other_tasks"]
    #
    #         day_salary = 0
    #
    #         if day_status == 1:  # Рабочий день по графику
    #             day_salary = (install_internet * COEFF_INT_WORKDAY) + \
    #                          (other_tasks * COEFF_OTHER_WORKDAY)
    #
    #         elif day_status == 0:  # Выходной день по графику
    #             # Если мастер работал в свой выходной, применяем повышенный коэффициент
    #             day_salary = (install_internet * COEFF_INT_WEEKEND) + \
    #                          (other_tasks * COEFF_OTHER_WEEKEND)
    #
    #         total_salary += day_salary
    #
    #     self.master["salary"] = total_salary
    #
    #     return total_salary

        # Поиск в БД без указания ТО
        # self.all_t_o = ["ТО Север", "ТО Юг", "ТО Запад", "ТО Восток"]

    # async def _get_schedule(self):
    #     cycle_str = self.master[0]["schedule"]
    #     cycle_parts = [int(p) for p in cycle_str.split('/')]    #
    #     # Рабочие дни (нечетные элементы)
    #     for i in range(0, len(cycle_parts), 2):
    #         self.schedule_list.extend([1] * cycle_parts[i])
    #         # Выходные дни (четные элементы)
    #         if i + 1 < len(cycle_parts):
    #             self.schedule_list.extend([0] * cycle_parts[i + 1])    #
    #     print(self.schedule_list)

    # # Получение даты для определения папки
    # async def _calc_date(self):
    #     today = datetime.now()
    #     target_date = today - timedelta(days=config.LAST_MONTH_DAYS_AGO)
    #     logger.info(f"Текущая дата: {today}")
    #     self.date_month_year = target_date.strftime("%m.%Y")

    # # Обработка всех файлов в цикле то и дней месяца
    # async def _read_jsons(self):
    #     for t_o in self.all_t_o:
    #         for day in self.month:
    #             try:
    #                 with open(f'files/{t_o}/{self.date_month_year}/{day}/{self.one_master}.json', 'r',
    #                           encoding='utf-8') as outfile:
    #                     data = json.loads(outfile.read())
    #                     self.masters[self.one_master]["et_int"] += data["et_int"]
    #                     self.masters[self.one_master]["et_int_pri"] += data["et_int_pri"]
    #                     self.masters[self.one_master]["et_tv"] +=  data["et_tv"]
    #                     self.masters[self.one_master]["et_tv_pri"] += data["et_tv_pri"]
    #                     self.masters[self.one_master]["et_dom"] += data["et_dom"]
    #                     self.masters[self.one_master]["et_dom_pri"] += data["et_dom_pri"]
    #                     self.masters[self.one_master]["et_serv"] += data["et_serv"]
    #                     self.masters[self.one_master]["et_serv_tv"] += data["et_serv_tv"]
    #                     self.masters[self.one_master]["all_tasks"] += data["et_int"] + data["et_tv"] + data["et_dom"] + data["et_serv"] + data["et_serv_tv"]
    #                     self.masters[self.one_master]["days"] += 1
    #             except FileNotFoundError:
    #                 ...     # Отсутствие отчета это нормально, ибо перебираем каждый день месяца


# Поиск отчетов в папке. Для вывода в тг, для сверки, после добавления или удаления отчетов.
class SearchReportsInFolder:
    def __init__(self, message, t_o, date_ago):
        self.message = message      # Сообщение из ТГ, необходимо для целевого ответа
        self.t_o = t_o              # Территориальное подразделение
        self.date_ago = date_ago              # Территориальное подразделение
        self.one_master = ""    # Фамилия мастера(название файла)
        self.num_reports = 0    # Количество отчетов в папке
        self.list_masters = []   # Список фамилий мастеров чей отчет есть в папке

    # Запуск всех методов для обработки
    async def process_report(self):
        await self._calc_date()             # Получение даты
        await self._search_files()          # Поиск файлов в папке
        await self._get_masters()           # Сбор фамилий мастеров по названиям файлов

    # Получение даты для определения папки
    async def _calc_date(self):
        # date_now = datetime.now()
        # date_ago = date_now - timedelta(hours=15)  # - hours здесь мы выставляем минус 15 часов
        # logger.info(f"Текущая дата: {date_now}")
        self.date_month_year = self.date_ago.strftime("%m.%Y")
        self.full_date = self.date_ago.strftime("%d.%m.%Y")

    # Поиск всех файлов в папке
    async def _search_files(self):
        if os.path.exists(f"files/{self.t_o}/{self.date_month_year}/{self.full_date}"):
            self.files = os.listdir(f"files/{self.t_o}/{self.date_month_year}/{self.full_date}")
            print(f"self.files {self.files}")

    # Сбор фамилий мастеров по названиям файлов
    async def _get_masters(self):
        for file in self.files:
            if file[-4:] == "json":
                self.list_masters.append(file[:-5])
                self.num_reports += 1

# # Вывод статистики по топам ко количеству заявок за день.
class TopsForDays:
    def __init__(self, message, month):
        self.message = message              # Сообщение из ТГ, необходимо для целевого ответа
        self.month = month      # Месяц, для поиска по БД
        self.statistic = {}     # Словарь всей статистики по всем то. (дата: то, то, то)
        self.better_statistic = {}  # Лучшая статистика из всех то.
        self.answer = ""
        self.answer_top = ""

    # Запуск всех методов для обработки
    async def process_report(self):
        await self._get_days()              # Перебор дней месяца
        # Статистика по дням для каждого ТО считается по цепочке в:
        # self._get_days() => _read_db() => _calc_top_for_one_to()

        await self._answer_one_to()         # Сбор ответа по статистикам для каждого ТО
        await self._calc_top_for_all_to()   # Подсчет лучшей статистики из всех ТО
        # await self._send_answer_to_chat()   # Отправка ответа в тг

    # Перебор дней месяца
    async def _get_days(self):
        for t_o in config.LIST_T_O:     # Переберем все ТО для раздельного поиска
            for day in self.month:
                if day not in self.statistic:
                    self.statistic[day] = {}
                await self._read_db(t_o, day)

    # Получение одного дня из бд
    async def _read_db(self, t_o, day):
        day_reports = crud.get_reports_for_day(date_full=day, t_o=t_o)
        await self._calc_top_for_one_to(t_o=t_o, day=day, day_reports=day_reports)

    # Топ за день для одного ТО.
    async def _calc_top_for_one_to(self, t_o, day, day_reports):
        tops_masters = []  # Мастер кто сделал больше всех заявок.(Мастера если количество совпало)
        top = 0
        for report in day_reports:
            master_all_tasks = report["et_int"] + report["et_tv"] + report["et_dom"] + report["et_serv"] + report["et_serv_tv"]
            # Очистим список мастеров если рекорд побит.
            if master_all_tasks > top:
                tops_masters.clear()
            # Добавим мастера, если количество его заявок больше или ровно последнему рекорду
            if master_all_tasks >= top:
                top = master_all_tasks
                tops_masters.append(report["master"])
        # self.statistic[day][t_o] = f"Заявок: {top}. {', '.join(tops_masters)}."
        self.statistic[day][t_o] = [top, tops_masters]

    async def _answer_one_to(self):
        for t_o in config.LIST_T_O:     # Переберем все ТО для раздельной статистики
            # answer = ""
            answer = f"\n\n{t_o}\n"
            for day in self.statistic:
                # answer += f"{day}: {self.statistic[day][t_o]} \n"
                # Для красивого вывода сместим если число в 1 символ
                if self.statistic[day][t_o][0] < 10:
                    answer += f"{day}: Заявок: {self.statistic[day][t_o][0]}.   {', '.join(self.statistic[day][t_o][1])} \n"
                else:
                    answer += f"{day}: Заявок: {self.statistic[day][t_o][0]}. {', '.join(self.statistic[day][t_o][1])} \n"
            await self._send_answer_to_chat(answer=answer)

    # Топ за день из всех ТО.
    async def _calc_top_for_all_to(self):
        answer = f"\n\nПо всем ТО:\n\n"
        for day in self.statistic:
            tops_masters = []  # Мастер(а) кто сделал больше всех заявок.(Мастера если количество совпало).
            top = 0  # Максимальное количество заявок.
            top_to = []  # ТО чей мастер сделал больше всех заявок. Или список ТО если количество совпало.
            answer_list = []
            self.better_statistic[day] = {}  # Добавим день с словарь.
            for t_o in config.LIST_T_O:
                if self.statistic[day][t_o][0] > top:
                    top_to.clear()
                    answer_list.clear()
                    tops_masters.clear()
                if self.statistic[day][t_o][0] >= top:
                    top = self.statistic[day][t_o][0]
                    top_to.append(t_o)
                    tops_masters.append(', '.join(self.statistic[day][t_o][1]))
            self.better_statistic[day] = [top_to, tops_masters]
            if len(top_to) > 1:
                if top < 10:
                    answer += f"{day}: Заявок: {top}.   {top_to[0]}. {' '*(10-len(top_to[0]))}Мастер(а):  {tops_masters[0]} \n"
                else:
                    answer += f"{day}: Заявок: {top}. {top_to[0]}. {' '*(10-len(top_to[0]))}Мастер(а):  {tops_masters[0]} \n"

                for one in range(1, len(top_to)):
                    if top < 10:
                        answer += f"{' '*21} Заявок: {top}.   {top_to[one]}. {' '*(10-len(top_to[one]))}Мастер(а):  {tops_masters[one]} \n"
                    else:
                        answer += f"{' '*21} Заявок: {top}. {top_to[one]}. {' '*(10-len(top_to[one]))}Мастер(а):  {tops_masters[one]} \n"

            else:
                if top < 10:
                    answer += f"{day}: Заявок: {top}.   {', '.join(top_to)}. {' '*(10-len(top_to[0]))}Мастер(а):  {', '.join(tops_masters)} \n"
                else:
                    answer += f"{day}: Заявок: {top}. {', '.join(top_to)}. {' '*(10-len(top_to[0]))}Мастер(а):  {', '.join(tops_masters)} \n"

        await self._send_answer_to_chat(answer=answer)
        # print(f"self.better_statistic {self.better_statistic}")
                


    # Отправка ответа в тг
    async def _send_answer_to_chat(self, answer):
        await self.message.answer(answer)
        # await self.message.answer(self.answer)
        # await self.message.answer(self.answer_top)