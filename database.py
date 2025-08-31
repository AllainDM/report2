
import sqlite3
import logging


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""Модуль для создания таблиц и соединения с БД"""

# Создание или подключение к базе данных SQLite
def get_sqlite_session():
    try:
        # Создаем соединение с базой данных и устанавливаем row factory
        conn = sqlite3.connect(f'database.db')
        conn.row_factory = sqlite3.Row  # Позволяет выводить данные в виде словаря
        return conn
    except Exception as e:
        logger.debug(f"Ошибка соединения с БД: {e}")
        return None


def updates_tables():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("create table if not exists full_day ("
                   "rowid integer primary key autoincrement, "
                   "t_o text not null, "
                   "et_int integer, "
                   "et_int_pri integer, "
                   "et_tv integer, "
                   "et_tv_pri integer, "
                   "et_dom integer, "
                   "et_dom_pri integer, "
                   "et_serv integer, "
                   "et_serv_tv integer, "
                   "data_month text, "
                   "date_full text, "
                   "record_time text"
                   ");")

    logger.debug("Таблица day создана.")
    conn.commit()

    cursor.execute("create table if not exists master_day ("
                   "rowid integer primary key autoincrement, "
                   "t_o text not null, "
                   "master text not null, "
                   "et_int integer, "
                   "et_int_pri integer, "
                   "et_tv integer, "
                   "et_tv_pri integer, "
                   "et_dom integer, "
                   "et_dom_pri integer, "
                   "et_serv integer, "
                   "et_serv_tv integer, "
                   "data_month text, "
                   "date_full text, "
                   "record_time text"
                   ");")

    logger.debug("Таблица day создана.")
    conn.commit()


    cursor.close()

updates_tables()
logger.debug(f"Модуль database отработал.")
