import json
import logging
from csv import excel

from datetime import datetime
from database import get_sqlite_session

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_master_day_report(master: str, t_o: str, report: dict, data_month: str, date_full: str, task_list: list):
    connection = get_sqlite_session()
    if connection is None:
        logging.debug("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:
        record_time = datetime.strftime(datetime.now(), "%d.%m.%Y %H:%M")

        # Преобразуем список в строку JSON
        task_list_json = json.dumps(task_list)

        # Сначала проверяем, есть ли такая запись
        cur.execute("SELECT rowid FROM master_day WHERE t_o = ? AND date_full = ? AND master = ?", (t_o, date_full, master))
        existing_record = cur.fetchone()

        if existing_record:
            # Если запись существует - удаляем ее
            cur.execute("DELETE FROM master_day WHERE t_o = ? AND date_full = ? AND master = ?", (t_o, date_full, master))
            logging.debug(f"Удалена существующая запись для t_o={t_o}, date_full={date_full}, master={master}")

        # Вставляем новую запись
        cur.execute("""
            INSERT INTO master_day 
            (t_o, master, et_int, et_int_pri, et_tv, et_tv_pri, et_dom, et_dom_pri, et_serv, et_serv_tv, 
            data_month, date_full, record_time, task_list) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t_o,
            master,
            report.get("et_int", 0),
            report.get("et_int_pri", 0),
            report.get("et_tv", 0),
            report.get("et_tv_pri", 0),
            report.get("et_dom", 0),
            report.get("et_dom_pri", 0),
            report.get("et_serv", 0),
            report.get("et_serv_tv", 0),
            data_month,
            date_full,
            record_time,
            task_list_json
        ))
        connection.commit()
        return True

    except Exception as ex:
        logging.info("Ошибка добавления данных в БД add_master_day_report", ex)

    finally:
        cur.close()
        connection.close()


def add_full_day_report(t_o: str, report: dict, data_month: str, date_full: str):
    connection = get_sqlite_session()
    if connection is None:
        logging.info("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:
        record_time = datetime.strftime(datetime.now(), "%d.%m.%Y %H:%M")
        # Сначала проверяем, есть ли такая запись
        cur.execute("SELECT rowid FROM full_day WHERE t_o = ? AND date_full = ?", (t_o, date_full))
        existing_record = cur.fetchone()

        if existing_record:
            # Если запись существует - удаляем ее
            cur.execute("DELETE FROM full_day WHERE t_o = ? AND date_full = ?", (t_o, date_full))
            logging.debug(f"Удалена существующая запись для t_o={t_o}, date_full={date_full}")

        # Вставляем новую запись
        cur.execute("""
            INSERT INTO full_day 
            (t_o, et_int, et_int_pri, et_tv, et_tv_pri, et_dom, et_dom_pri, et_serv, et_serv_tv, data_month, date_full, record_time) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            date_full,
            record_time
        ))
        connection.commit()
        return True

    except Exception as ex:
        logging.debug("Ошибка добавления данных в БД add_full_day_report", ex)

    finally:
        cur.close()
        connection.close()

# Проверка все ли ТО сделали дневной отчет.
def check_all_full_day_report(date_full: str):
    connection = get_sqlite_session()
    if connection is None:
        logging.debug("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:
        # Считаем количество записей на эту дату
        cur.execute("SELECT COUNT(*) FROM full_day WHERE date_full = ?", (date_full,))
        result = cur.fetchone()

        # Если есть ровно 4 записи, иначе False
        if result is not None and result[0] == 4:
            print("Есть 4 записи ТО")
        else:
            print("Еще не все сделали дневной отчет.")
        return result is not None and result[0] == 4

    except Exception as ex:
        logging.debug("Ошибка при проверке количества записей", ex)
        return False

    finally:
        cur.close()
        connection.close()

def get_average_day_statistic_for_all_to(date_full: str):
    connection = get_sqlite_session()
    if connection is None:
        logging.debug("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:

        cur.execute("""
            SELECT
                t_o,
                COUNT(master) AS master_count,
                SUM(et_int + et_tv + et_dom + et_serv + et_serv_tv) AS total_requests,
                AVG(et_int + et_tv + et_dom + et_serv + et_serv_tv) AS average_requests_per_master
            FROM
                master_day
            WHERE
                date_full = ?
            GROUP BY
                t_o;
        """, (date_full,))
        results = cur.fetchall()
        return results

    except Exception as ex:
        logging.debug("Ошибка при средней дневной статистики", ex)
        return False

    finally:
        cur.close()
        connection.close()


def delete_master_day_report(date_full: str, master: str, t_o: str):
    """
    Удаляет запись из таблицы master_day по дате и имени мастера.
    :param date_full: Полная дата (например, '05.09.2025').
    :param master: Имя мастера.
    :param t_o: Терр отделение где необходимо удалить отчет.
    :return: True, если удаление прошло успешно, иначе False.
    """
    print(f'Запрос на удаление: "{master}", "{date_full}", "{t_o}"')
    connection = get_sqlite_session()
    if connection is None:
        logging.debug("Ошибка: не удалось подключиться к базе данных.")
        return False

    cur = connection.cursor()
    try:
        # SQL-запрос для удаления записи
        sql_query = "DELETE FROM master_day WHERE date_full = ? AND master = ? AND t_o = ?"

        # Выполняем запрос с параметрами
        cur.execute(sql_query, (date_full, master, t_o))

        # Фиксируем изменения в базе данных
        connection.commit()

        logging.info(f"Запись для мастера '{master}' для {t_o} на дату '{date_full}' успешно удалена.")
        return True

    except Exception as ex:
        logging.error(f"Ошибка при удалении записи: {ex}")
        return False

    finally:
        cur.close()
        connection.close()

