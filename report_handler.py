
import json
import logging

from aiogram.types import FSInputFile

import parser
import to_exel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Класс парсера отчета мастера
class ReportParser:
    def __init__(self, message, t_o, date_now_full, month_year):
        self.message = message  # Сообщение из ТГ
        self.main_txt = ""      # Разобранное сообщения для обработки парсером
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
            await self._validate_master()   # Если не указана фамилия, обрабатывать дальше нет смысла.
            await self._parse_report()      # Сбор количества выполненных заявок
            await self._validate_error()    # Обработка ошибок, отсутствия необходимых пунктов
            await self._collect_repair_numbers()        # Составление списка номеров сервисов
            await self._save_report_json()
            await self._send_parsed_report_to_chat()    # Отправим обработанный отчет текстов в чат
        except ValueError as e:
            await self.message.reply(str(e))
            return

    # Обработка сообщения, разделение по ":"
    async def _parse_message(self):
        # TODO Разбивка по ":" старый способ, по нему определялся провайдер.
        # TODO Добавить проверку если будут проблемы
        # Разбиваем по ":", так мы определим что это отчет.
        pre_txt_lower = self.message.text.lower()
        logger.info(f"pre_txt_lower {pre_txt_lower}")
        # Мастера могут добавлять лишние ":" при перечислении.
        pre_txt = (pre_txt_lower.replace("тв:", "тв").
                   replace("ис:", "ис").
                   replace("нет:", "нет").
                   replace("он:", "он"))
        logger.info(f"pre_txt {pre_txt}")
        self.main_txt = pre_txt.split(":")
        logger.info(f"self.main_txt {self.main_txt}")

    # Определение мастера
    async def _validate_master(self):
        # Если в начале сообщения есть фамилия, то возьмем ее.
        txt_soname_pre = self.main_txt[0].replace("\n", " ")
        txt_soname = txt_soname_pre.split(" ")
        if txt_soname[0][0:2].lower() != 'ет':
            if txt_soname[0][0:2].lower() == "то":
                raise ValueError("Необходимо указать фамилию мастера, отчет не сохранен.")
                # await self.message.reply("Необходимо указать фамилию мастера, отчет не сохранен 1.")
                # return
            else:
                self.master = txt_soname[0].title()
        if self.master == "не указан" or self.master == "":
            raise ValueError("Необходимо указать фамилию мастера, отчет не сохранен.")
            # await self.message.reply("Необходимо указать фамилию мастера, отчет не сохранен 2.")
            # return

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
                # logger.info(new_txt_list)

        # Вычисление привлеченных, а так же поиск ошибки отсутствия нужного количества слов "прив" в отчете.
        # Перебор отчета, первый привлеченный идет в интернет, второй в тв, третий в домофон.
        # Флаги для правильности перебора
        flag_priv_int = 0
        flag_priv_tv = 0
        flag_priv_dom = 0
        for num, val in enumerate(new_txt_list):
            if val[0:4].lower() == "прив":
                if flag_priv_int == 0:  # Флаг привлеченного интернета
                    # logger.info(f"тут привлеченный интернет {new_txt_list[num - 1]}")
                    flag_priv_int = 1
                    try:
                        self.et_int_pri = int(new_txt_list[num - 1])  # Перед "прив"
                        if self.et_int_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_int_pri_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_int_pri = 0
                elif flag_priv_tv == 0:  # Флаг привлеченного тв
                    # logger.info(f"тут привлеченный тв {new_txt_list[num - 1]}")
                    flag_priv_tv = 1
                    try:
                        self.et_tv_pri = int(new_txt_list[num - 1])  # Перед "прив"
                        if self.et_tv_pri < 100:  # Проверка на длину значения, защита от номера сервиса
                            self.et_tv_pri_flag = 1  # Флаг для проверки правильности отчета
                    except ValueError:
                        self.et_tv_pri = 0
                elif flag_priv_dom == 0:  # Флаг привлеченного домофона
                    # logger.info(f"тут привлеченный домофон {new_txt_list[num - 1]}")
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
        logger.info(f"repairs_txt_et {repairs_txt_et}")

        # Добавляем в список все 7-ми значные номера
        for i in repairs_txt_et_list:
            if len(i) == 7 and i.isnumeric():
                self.list_repairs.append(['ЕТ', i, self.master])

    # Сохранение отчета в json
    async def _save_report_json(self):
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
            json.dump(data, f)

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

# Класс вывода отчета
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
        # Старый способ, не работает в новом aiogram
        # exel = open(f"files/{self.t_o}/{self.date_month_year}/{self.report_folder}.xls", "rb")
        # await self.message.answer_document(exel)


