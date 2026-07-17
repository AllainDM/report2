import sqlite3
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def migrate_tables():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Список новых колонок
    new_columns = ["etm_ko", "etm_mo", "etm_all_devices"]
    tables = ["full_day", "master_day"]

    for table in tables:
        for column in new_columns:
            try:
                # Используем OR IGNORE или просто обработку исключения,
                # если колонка уже существует
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} integer;")
                logger.info(f"Колонка {column} добавлена в таблицу {table}.")
            except sqlite3.OperationalError:
                logger.warning(f"Колонка {column} уже существует в таблице {table} или ошибка выполнения.")

    conn.commit()
    cursor.close()
    conn.close()


# Вызов функции
migrate_tables()

