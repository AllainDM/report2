import os
import json
import logging
from datetime import datetime, timedelta

from aiogram.types import FSInputFile

import parser
import config
import to_exel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Исключение для ошибок валидации"""
    pass

# Класс парсера отчета из сообщения мастера
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
            # Вызов из функции обработки даты
            # await self._validate_master()   # Если не указана фамилия, обрабатывать дальше нет смысла
            await self._parse_report()      # Сбор количества выполненных заявок
            await self._validate_error()    # Обработка ошибок, отсутствия необходимых пунктов
            await self._collect_repair_numbers()        # Составление списка номеров сервисов
            await self._save_report_json()
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
                raise ValidationError("Отправка отчета с датой смертным запрещена, отчет не сохранен.")

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
        if txt_soname[0][0:2].lower() != 'ет':
            if txt_soname[0][0:2].lower() == "то":
                raise ValidationError("Необходимо указать фамилию мастера, отчет не сохранен.")
            else:
                self.master = txt_soname[0].title()
        if self.master == "не указан" or self.master == "":
            raise ValidationError("Необходимо указать фамилию мастера, отчет не сохранен.")


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
            await self.message.reply(f"Внимание, возможна ошибка с отчетом мастера "
                                     f"{self.master}: {msg_err_txt} Отчет не сохранен.")
            return

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

# Вывод отчета за день
class ReportCalc:
    def __init__(self, message, t_o, files, date_month_year, report_folder):
        self.message = message              # Сообщение из ТГ
        self.t_o = t_o                      # Территориальное отделение
        self.files = files                  # Список с файлами в папке с отчетами за день
        self.date_month_year = date_month_year  # Имя папки(месяц/год) с отчетами за месяц
        self.report_folder = report_folder      # Имя папки(день/месяц/год) с отчетами за день

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
        await self._read_jsons()            # Чтение файлов json в папке
        await self._send_answer_to_chat()   # Отправка ответа со списком мастеров в чат
        await self._save_report_json()      # Сохраним в json общее количество выполненных задач и все их номера
        await self._parser_address()        # Получим адреса и типы всех задач
        await self._save_report_exel()      # Сохраним результат парсера в ексель
        await self._send_exel_to_chat()     # Отправим ексель файл в чат тг

    # Чтение файлов с отчетами за день. Извлечение количества выполненных заявок и списка номеров заданий.
    async def _read_jsons(self):
        for file in self.files:
            if file[-4:] == "json":
                with open(f'files/{self.t_o}/{self.date_month_year}/{self.report_folder}/{file}', 'r', encoding='utf-8') as outfile:
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

    # Отправим обработанный отчет текстов в чат
    async def _send_answer_to_chat(self):
        # Выведем имена мастеров для сверки
        answer = "Получены отчеты: \n"
        for master in self.list_masters:
            answer += f'{master} \n'
        await self.message.answer(answer)

    # Сохранение отчета в json
    async def _save_report_json(self):
        # Сохраним в json файл итоговый результат
        with open(f'files/{self.t_o}/{self.date_month_year}/{self.report_folder}.json', 'w') as outfile:
            json.dump(self.to_save, outfile, sort_keys=False, ensure_ascii=False, indent=4, separators=(',', ': '))

    # Получение адресов по списку номеров заданий
    async def _parser_address(self):
        # Получим обработанный список из парсера
        self.parser_answer = await parser.get_address(self.to_save["list_repairs"])

    # Сохранение отчета в exel
    async def _save_report_exel(self):
        # Сохраним ексель файл с номерами ремонтов
        await to_exel.save_to_exel(list_to_exel=self.parser_answer, t_o=self.t_o,
                                   full_date=self.report_folder, date_month_year=self.date_month_year)

    # Отправка exel файла в чат
    async def _send_exel_to_chat(self):
        file = FSInputFile(f"files/{self.t_o}/{self.date_month_year}/{self.report_folder}.xls",
                           filename=f"{self.report_folder}.xls")
        await self.message.answer_document(file)

# Сбор недельной статистики
class ReportWeek:
    def __init__(self, message, t_o, week, date_month_year):
        self.message = message              # Сообщение из ТГ
        self.t_o = t_o                      # Территориальное отделение
        self.week = week                        # 7 дат прошлой недели
        self.date_month_year = date_month_year  # Имя папки(месяц/год) с отчетами за месяц
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
            await self._get_files(day)

    # Получение всех файлов в папке одного дня
    async def _get_files(self, day):
        if os.path.exists(f"files/{self.t_o}/{self.date_month_year}/{day}"):
            files = os.listdir(f"files/{self.t_o}/{self.date_month_year}/{day}")
            await self._read_jsons(files, day)

    # Обработка файлов одного дня
    async def _read_jsons(self, files, day):
        for file in files:
            if file[-4:] == "json":
                with open(f'files/{self.t_o}/{self.date_month_year}/{day}/{file}', 'r',
                          encoding='utf-8') as outfile:
                    data = json.loads(outfile.read())
                    self.to_save["et_int"] += data["et_int"]
                    self.to_save["et_int_pri"] += data["et_int_pri"]
                    self.to_save["et_tv"] += data["et_tv"]
                    self.to_save["et_tv_pri"] += data["et_tv_pri"]
                    self.to_save["et_dom"] += data["et_dom"]
                    self.to_save["et_dom_pri"] += data["et_dom_pri"]
                    self.to_save["et_serv"] += data["et_serv"]
                    self.to_save["et_serv_tv"] += data["et_serv_tv"]

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
        self.message = message              # Сообщение из ТГ
        self.t_o = t_o                      # Территориальное отделение
        self.month = month          # Даты нужного месяца
        self.date_month_year = ""   # Имя папки(месяц/год) с отчетами за месяц
        self.masters = {}

    # Запуск всех методов для обработки обсчета статистики
    async def process_report(self):
        await self._calc_date()             # Получение даты
        await self._get_days()              # Перебор дней месяца
        await self._send_answer_to_chat()   # Отправка ответа в тг

    # Получение даты для определения папки
    async def _calc_date(self):
        date_now = datetime.now()
        logger.info(f"MastersStatistic Текущая дата: {date_now}")
        self.date_month_year = date_now.strftime("%m.%Y")

    # Перебор дней месяца
    async def _get_days(self):
        for day in self.month:
            await self._get_files(day)

    # Получение всех файлов в папке одного дня
    async def _get_files(self, day):
        if os.path.exists(f"files/{self.t_o}/{self.date_month_year}/{day}"):
            files = os.listdir(f"files/{self.t_o}/{self.date_month_year}/{day}")
            await self._read_jsons(files, day)

    # Обработка файлов одного дня
    async def _read_jsons(self, files, day):
        for file in files:
            if file[-4:] == "json":
                master = file[:-5]
                with open(f'files/{self.t_o}/{self.date_month_year}/{day}/{file}', 'r',
                          encoding='utf-8') as outfile:
                    data = json.loads(outfile.read())
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
                            "days": 0,
                        }
                    self.masters[master]["et_int"] += data["et_int"]
                    self.masters[master]["et_int_pri"] += data["et_int_pri"]
                    self.masters[master]["et_tv"] +=  data["et_tv"]
                    self.masters[master]["et_tv_pri"] += data["et_tv_pri"]
                    self.masters[master]["et_dom"] += data["et_dom"]
                    self.masters[master]["et_dom_pri"] += data["et_dom_pri"]
                    self.masters[master]["et_serv"] += data["et_serv"]
                    self.masters[master]["et_serv_tv"] += data["et_serv_tv"]
                    self.masters[master]["all_tasks"] += data["et_int"] + data["et_tv"] + data["et_dom"] + data["et_serv"] + data["et_serv_tv"]
                    self.masters[master]["days"] += 1

    # Отправка ответа в тг
    async def _send_answer_to_chat(self):
        for master in self.masters:
            answer = (f"{master} \n\n"
                      # f"Выполнено: \n"
                      f"Интернет {self.masters[master]["et_int"]} "
                      f"({self.masters[master]["et_int_pri"]}), \n"
                      f"ТВ {self.masters[master]["et_tv"]}({self.masters[master]["et_tv_pri"]}), \n"
                      f"Домофон {self.masters[master]["et_dom"]}({self.masters[master]["et_dom_pri"]}), \n"
                      f"Сервис {self.masters[master]["et_serv"]}, \n"
                      f"Сервис ТВ {self.masters[master]["et_serv_tv"]} \n\n"
                      f"Всего выполнено: {self.masters[master]["all_tasks"]} \n"
                      f"Отработано смен: {self.masters[master]["days"]} \n"
                      f"Среднее за смену: {round(self.masters[master]["all_tasks"]/self.masters[master]["days"], 1)} \n"
                      )

            await self.message.answer(answer)

# Вывода статистики одного мастера по всем то
class OneMasterStatistic:
    def __init__(self, message, one_master, month):
        self.message = message      # Сообщение из ТГ
        self.one_master = one_master
        self.masters = {one_master: {
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
        }}
        self.month = month          # Даты нужного месяца
        self.date_month_year = ""   # Имя папки(месяц/год) с отчетами за месяц
        self.all_t_o = ["ТО Север", "ТО Юг", "ТО Запад", "ТО Восток"]

    # Запуск всех методов для обработки обсчета статистики
    async def process_report(self):
        await self._calc_date()             # Получение даты
        await self._read_jsons()            # Перебор дней месяца
        await self._send_answer_to_chat()   # Отправка ответа в тг

    # Получение даты для определения папки
    async def _calc_date(self):
        date_now = datetime.now()
        logger.info(f"Текущая дата: {date_now}")
        self.date_month_year = date_now.strftime("%m.%Y")

    # Обработка всех файлов в цикле то и дней месяца
    async def _read_jsons(self):
        for t_o in self.all_t_o:
            for day in self.month:
                try:
                    with open(f'files/{t_o}/{self.date_month_year}/{day}/{self.one_master}.json', 'r',
                              encoding='utf-8') as outfile:
                        data = json.loads(outfile.read())
                        self.masters[self.one_master]["et_int"] += data["et_int"]
                        self.masters[self.one_master]["et_int_pri"] += data["et_int_pri"]
                        self.masters[self.one_master]["et_tv"] +=  data["et_tv"]
                        self.masters[self.one_master]["et_tv_pri"] += data["et_tv_pri"]
                        self.masters[self.one_master]["et_dom"] += data["et_dom"]
                        self.masters[self.one_master]["et_dom_pri"] += data["et_dom_pri"]
                        self.masters[self.one_master]["et_serv"] += data["et_serv"]
                        self.masters[self.one_master]["et_serv_tv"] += data["et_serv_tv"]
                        self.masters[self.one_master]["all_tasks"] += data["et_int"] + data["et_tv"] + data["et_dom"] + data["et_serv"] + data["et_serv_tv"]
                        self.masters[self.one_master]["days"] += 1
                except FileNotFoundError:
                    ...

    # Отправка ответа в тг
    async def _send_answer_to_chat(self):
        answer = (f"{self.one_master} \n\n"
                  # f"Выполнено: \n"
                  f"Интернет {self.masters[self.one_master]["et_int"]} "
                  f"({self.masters[self.one_master]["et_int_pri"]}), \n"
                  f"ТВ {self.masters[self.one_master]["et_tv"]}({self.masters[self.one_master]["et_tv_pri"]}), \n"
                  f"Домофон {self.masters[self.one_master]["et_dom"]}({self.masters[self.one_master]["et_dom_pri"]}), \n"
                  f"Сервис {self.masters[self.one_master]["et_serv"]}, \n"
                  f"Сервис ТВ {self.masters[self.one_master]["et_serv_tv"]} \n\n"
                  f"Всего выполнено: {self.masters[self.one_master]["all_tasks"]} \n"
                  f"Отработано смен: {self.masters[self.one_master]["days"]} \n"
                  f"Среднее за смену: {round(self.masters[self.one_master]["all_tasks"] / self.masters[self.one_master]["days"], 1)} \n"
                  )
        await self.message.answer(answer)

# Поиск отчетов в папке. Для вывода в тг, для сверки, после добавления или удаления отчетов.
class SearchReportsInFolder:
    def __init__(self, message, t_o):
        self.message = message      # Сообщение из ТГ
        self.t_o = t_o              # Территориальное подразделение
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
        date_now = datetime.now()
        date_ago = date_now - timedelta(hours=15)  # - hours здесь мы выставляем минус 15 часов
        logger.info(f"Текущая дата: {date_now}")
        self.date_month_year = date_ago.strftime("%m.%Y")
        self.full_date = date_ago.strftime("%d.%m.%Y")

    # Поиск всех файлов в папке
    async def _search_files(self):
        if os.path.exists(f"files/{self.t_o}/{self.date_month_year}/{self.full_date}"):
            self.files = os.listdir(f"files/{self.t_o}/{self.date_month_year}/{self.full_date}")

    # Сбор фамилий мастеров по названиям файлов
    async def _get_masters(self):
        for file in self.files:
            if file[-4:] == "json":
                self.list_masters.append(file[:-5])
                self.num_reports += 1
