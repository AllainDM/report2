import os
import re
import time
import logging
from importlib.metadata import files

import lxml
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

import config


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Загрузка переменных окружения из файла .env
load_dotenv()


class Parser:
    """
    Класс парсера основного биллинга.
    Управляет аутентификацией и извлечением данных.
    """
    URL_LOGIN_GET = "https://us.gblnet.net/"
    URL_LOGIN = "https://us.gblnet.net/body/login"
    BASE_URL = "https://us.gblnet.net"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:105.0) Gecko/20100101 Firefox/105.0"
    }

    def __init__(self, username, password):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.csrf_token = None
        self.is_logged_in = False


    def _get_csrf_token(self):
        """Извлекает CSRF токен из скриптов на странице логина."""
        try:
            req = self.session.get(self.URL_LOGIN_GET, headers=self.HEADERS, timeout=10)
            soup = BeautifulSoup(req.content, 'html.parser')
            # Используем regex для поиска токена
            script_content = soup.find('script', string=re.compile(r'_csrf:'))
            if script_content:
                match = re.search(r'_csrf:\s*\'([^\']+)\'', script_content.string)
                if match:
                    self.csrf_token = match.group(1)
                    logger.info(f"CSRF токен получен: {self.csrf_token}")
                    return True

            logger.error("Не удалось найти CSRF токен.")
            return False
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении токена: {e}")
            return False


    def login(self):
        """
        Выполняет аутентификацию и создает сессию.
        """
        if self.is_logged_in:
            logger.info("Сессия уже активна.")
            return True

        if not self._get_csrf_token():
            return False

        data = {
            "_csrf": self.csrf_token,
            "return_page": "",
            "username": self.username,
            "password": self.password,
        }

        try:
            response = self.session.post(self.URL_LOGIN, data=data, headers=self.HEADERS, timeout=10)
            if response.status_code == 200 and 'dashboard' in response.url:
                logger.info("Аутентификация успешна. Сессия создана.")
                self.is_logged_in = True
                return True
            else:
                logger.error(f"Аутентификация не удалась. Код ответа: {response.status_code}")
                self.is_logged_in = False
                return False
        except requests.RequestException as e:
            logger.error(f"Ошибка при создании сессии: {e}")
            self.is_logged_in = False
            return False

    async def get_address(self, list_repairs):
        """
        Асинхронно обрабатывает список ремонтов и извлекает информацию по адресу.
        """
        if not self.is_logged_in and not self.login():
            logger.error("Не удалось залогиниться. Прекращение работы.")
            return list_repairs

        for item in list_repairs:
            service_id = item[1]
            link = f"{self.BASE_URL}/task/{service_id}"

            logger.info(f"Получение данных по задаче: {service_id}, ссылка: {link}")
            time.sleep(1)  # Используйте config.DELAY, если он есть

            try:
                response = self.session.get(link, headers=self.HEADERS, timeout=15)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    table = soup.find('table', class_="j_table")

                    if not table:
                        self._handle_parsing_error(item, "Не найдена таблица с данными.")
                        continue

                    # Извлекаем тип задачи
                    task_type_span = soup.find(class_="label_h2").find('span')
                    task_type = task_type_span.text.strip() if task_type_span else ""
                    item.append(task_type)

                    # Поиск адреса и данных о клиенте
                    address_link = table.find('a', string=re.compile(r'Россия'))

                    if address_link:
                        address_str = address_link.text.strip()
                        street, house, apartment = self._parse_address(address_str)
                        item.append([street, house, apartment, address_str])

                        user_id, user_ls = self._find_user_info(table)
                        item.append(user_ls)
                        item.append(user_id)

                    else:
                        self._handle_parsing_error(item, "Адрес не найден.")

                else:
                    logger.warning(f"Ошибка HTTP: {response.status_code} для ссылки {link}")
                    self._handle_parsing_error(item, f"Ошибка HTTP {response.status_code}.")

            except requests.RequestException as e:
                logger.error(f"Ошибка запроса для {link}: {e}")
                self._handle_parsing_error(item, f"Ошибка соединения: {e}.")

        return list_repairs

    def _handle_parsing_error(self, item, message):
        """Вспомогательный метод для обработки ошибок парсинга и добавления информации в список."""
        logger.warning(f"Ошибка парсинга для задачи: {item[1]}. Сообщение: {message}")
        item.extend([" ", " ", " ", " "])  # Добавляем пустые поля для сохранения структуры
        item.append(f"!!! {message}")

    def _find_user_info(self, table):
        """Извлекает ID пользователя и номер договора (ЛС) из таблицы."""
        user_id = ""
        user_ls = ""

        # Поиск по регулярным выражениям
        text_content = table.text
        id_match = re.search(r'ID:\s*(\d+)', text_content)
        if id_match:
            user_id = id_match.group(1)

        ls_match = re.search(r'договор:\s*([^\s]+)', text_content)
        if ls_match:
            user_ls = ls_match.group(1)

        # Специальная обработка для "счет:" (если логин с "_" не подходит)
        if "_" in user_ls:
            full_info = table.find(class_="taskCustomerFullInfo")
            if full_info:
                ls_match_full = re.search(r'счет:\s*([^\s]+)', full_info.text)
                if ls_match_full:
                    user_ls = ls_match_full.group(1)

        return user_id, user_ls

    def _parse_address(self, full_address):
        """
        Парсит полную строку адреса на улицу, дом и квартиру.
        """
        logger.info(f"Парсинг адреса: {full_address}")

        # Очистка и приведение к стандартному виду
        full_address = full_address.replace("ул.", "").replace("б-р", "").replace("ш.", "").strip()

        # Регулярное выражение для извлечения адреса:
        # 1. 'Россия, ...' - пропускаем
        # 2. 'город/населенный пункт, ...' - пропускаем
        # 3. 'улица' - всё до слова 'дом' или 'д.'
        # 4. 'дом' - число с буквой/корпусом
        # 5. 'кв.' - число или диапазон
        regex = r'Россия, [^,]+, ([^,]+), [^,]+, (?:дом|д\.)\s*([\d\w/кК]+)(?:,\s*кв\.?\s*([^\s]+))?'
        match = re.search(regex, full_address)

        if match:
            street_raw = match.group(1).strip()
            house = match.group(2).replace('/', 'к')
            apartment = match.group(3) if match.group(3) else 'н/д'

            street = self._cut_street_name(street_raw)
            return street, house, apartment

        logger.warning(f"Не удалось распарсить адрес: {full_address}")
        return "н/д", "н/д", "н/д"

    def _cut_street_name(self, street):
        """Корректирует названия улиц по словарю."""
        corrections = {
            "реки Смоленки": "Смоленки",
            "Набережная Фонтанки": "Фонтанки",
            "Канонерский остров": "Канонерский",
            "Воскресенская (Робеспьера)": "Воскресенская",
            "Петровская": "Петровская коса",
            "Октябрьская": "Октябрьская наб.",
            "Волковский пр.": "Волковский",
            "Парголово": "Парголово",
            "Шушары": "Шушары",
            "Новое Девяткино дер.": "Новое Девяткино",
            "пос. Шушары": "Шушары",
            "Кудрово": "Кудрово",
            "Мурино": "Мурино",
            "Бугры пос.": "Бугры",
            "Репино": "Репино",
            "Сестрорецк": "Сестрорецк",
            "Песочный": "Песочный",
            "Лисий": "Лисий",
            "Горелово": "Горелово",
            "Коммунар": "Коммунар",
            "Колпино": "Колпино",
            "Горская": "Горская",
            "Понтонный": "Понтонный",
            "Тельмана": "Тельмана",
            "Тельмана пос.": "Тельмана",
            "Стрельна": "Стрельна",
            "пос. Стрельна": "Стрельна",
            "Новогорелово пос.": "Новогорелово",
            "Новогорелово": "Новогорелово"
        }
        return corrections.get(street, street)