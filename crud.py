
import logging
from csv import excel

from datetime import datetime
from database import get_sqlite_session

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_day_report(t_o: str, report: dict, data_month: str, date_full: str):
    connection = get_sqlite_session()
    if connection is None:
        logging.debug("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:
        # Сначала проверяем, есть ли такая запись
        cur.execute("SELECT rowid FROM day WHERE t_o = ? AND date_full = ?", (t_o, date_full))
        existing_record = cur.fetchone()

        if existing_record:
            # Если запись существует - удаляем ее
            cur.execute("DELETE FROM day WHERE t_o = ? AND date_full = ?", (t_o, date_full))
            logging.debug(f"Удалена существующая запись для t_o={t_o}, date_full={date_full}")

        # Вставляем новую запись
        cur.execute("""
            INSERT INTO day 
            (t_o, et_int, et_int_pri, et_tv, et_tv_pri, et_dom, et_dom_pri, et_serv, et_serv_tv, data_month, date_full) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t_o,
            report.get("et_int", 0),
            report.get("et_int_pri", 0),
            report.get("et_tv", 0),
            report.get("et_tv_pri", 0),
            report.get("et_dom", 0),
            report.get("et_dom_pri", 0),
            report.get("et_serv", 0),
            report.get("et_serv_tv", 0),
            data_month,
            date_full
        ))
        connection.commit()
        return True

    except Exception as ex:
        logging.debug("Ошибка добавления данных в БД 1", ex)

    finally:
        cur.close()
        connection.close()
