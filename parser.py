
import re
import time
import logging
from importlib.metadata import files

import requests
from bs4 import BeautifulSoup
import lxml

import config


# Настройка логирования
logging.basicConfig(level=logging.INFO)

logging.debug("Это отладочное сообщение")
logging.info("Это информационное сообщение")
logging.warning("Это предупреждение")
logging.error("Это ошибка")
logging.critical("Это критическая ошибка")

logger = logging.getLogger(__name__)


url_login_get = "https://us.gblnet.net/"
url_login = "https://us.gblnet.net/body/login"
url = "https://us.gblnet.net/dashboard"


HEADERS = {
    "main": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:105.0) Gecko/20100101 Firefox/105.0"
}

data_users = {
    "_csrf": '',
    "return_page": "",
    "username": config.loginUS,
    "password": config.pswUS
}

session_users = requests.Session()

req = session_users.get(url_login_get)

csrf = None

def get_token():
    global csrf
    soup = BeautifulSoup(req.content, 'html.parser')
    logger.info("###################")
    scripts = soup.find_all('script')

    for script in scripts:
        if script.string is not None:
            # print(script.string)
            script_lst = script.string.split(" ")
            # print(script_lst)
            for num, val in enumerate(script_lst):
                if val == "_csrf:":
                    csrf = script_lst[num+1]
    logger.info(f"csrf {csrf}")



def create_users_sessions():
    global csrf
    while True:
        try:
            get_token()
            data_users["_csrf"] = csrf[1:-3]
            response_users2 = session_users.post(url_login, data=data_users, headers=HEADERS).text
            logger.info("Сессия Юзера создана 2")
            # print(response_users2)
            return response_users2
        except ConnectionError:
            logger.info("Ошибка создания сессии")
            # TODO функция отправки тут отсутствует
            # send_telegram("Ошибка создания сессии UserSide, повтор запроса через 5 минут")
            # time.sleep(300)


response_users = create_users_sessions()

