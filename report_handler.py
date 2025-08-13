
import json
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Класс отчета мастера
class ReportHandler:
    def __init__(self, message, t_o, date_now_year, date_now_no_year, month_year):
        self.message = message  # Сообщение из ТГ
        self.main_txt = ""      # Разобранное сообщения для обработки парсером
        self.t_o = t_o          # Территориальное подразделение
        self.date_now_year = date_now_year      # Обсчитанная дата с годом
        self.date_now_no_year = date_now_year   # Обсчитанная дата без года
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
        await self._parse_message()     # Обработка сообщения, разделение по ":"
        await self._validate_master()   # Если не указана фамилия, обрабатывать дальше нет смысла.
        await self._parse_report()      # Сбор количества выполненных заявок
        await self._validate_error()    # Обработка ошибок, отсутствия необходимых пунктов
        await self._collect_repair_numbers()        # Составление списка номеров сервисов
        await self._save_report()
        await self._send_parsed_report_to_chat()    # Отправим обработанный отчет текстов в чат

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
                await self.message.reply("Необходимо указать фамилию мастера, отчет не сохранен.")
                return
            else:
                self.master = txt_soname[0].title()
        if self.master == "не указан" or self.master == "":
            await self.message.reply("Необходимо указать фамилию мастера, отчет не сохранен.")
            return

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

        for i in repairs_txt_et_list:
            if len(i) == 7 and i.isnumeric():
                self.list_repairs.append(['ЕТ', i, self.master])

    # Сохранение отчета
    async def _save_report(self):
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
        with open(f'files/{self.t_o}/{self.month_year}/{self.date_now_year}/{self.master}.json', 'w') as f:
            json.dump(data, f)

    # Отправим обработанный отчет текстов в чат
    async def _send_parsed_report_to_chat(self):
        answer = (f"{self.t_o} {self.date_now_no_year}. Мастер {self.master} \n\n"
                  f"Интернет {self.et_int}"
                  f"({self.et_int_pri}), "
                  f"ТВ {self.et_tv}({self.et_tv_pri}), "
                  f"домофон {self.et_dom}({self.et_dom_pri}), "
                  f"сервис {self.et_serv}, "
                  f"сервис ТВ {self.et_serv_tv}")

        await self.message.answer(answer)

