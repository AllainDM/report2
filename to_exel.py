import json
import xlwt

def save_to_exel(list_to_exel, t_o, date, month_year, id_ls):
    # print("Запуск функции сохранения в ексель файл.")
    wb = xlwt.Workbook()
    ws = wb.add_sheet(date)
    list_repairs_for_json = []

    for n, v in enumerate(list_to_exel):
        ws.write(n+1, 0, v[0])  # Бренд
        ws.write(n+1, 1, date)  # Дата
        ws.write(n+1, 2, v[5])  # ЛС. Под 5 индексом должны быть ИД и ЛС
        ws.write(n+1, 3, v[1])  # Номер
        ws.write(n+1, 7, v[2])  # Мастер
        ws.write(n+1, 4, v[3][0])  # Улица
        ws.write(n+1, 5, v[3][1])  # Дом
        ws.write(n+1, 6, v[3][2])  # Квартира
        ws.write(n+1, 8, v[6])  # ИД
        ws.write(n+1, 9, v[4])  # Тип задания
        ws.write(n+1, 26, v[3][3])  # Полный адрес
        ws.write(n+1, 17, f"=ГИПЕРССЫЛКА(CONCAT($Y$2;D{n+2});D{n+2})")  # Ссылка
        # Добавим в json для файлика отчета
        list_repairs_for_json.append(
            {"brand": v[0],  # Бренд
             "date": date,  # Дата
             "num-ls": "",  # Номер договора. Пока пусто
             "num-serv": v[1],  # Номер заявки
             "street": v[3][0],  # Улица
             "dom": v[3][1],  # Номер дома
             "kv": v[3][2],  # Номер квартиры
             "master": v[2],  # Мастер
             })
    # Гиперссылка
    ws.write(1, 24, "https://us.gblnet.net/task/")

    with open(f'files/{t_o}/{month_year}/{date}_list.json', 'w') as outfile:
        json.dump(list_repairs_for_json, outfile, sort_keys=False, ensure_ascii=False, indent=4, separators=(',', ': '))

    wb.save(f'files/{t_o}/{month_year}/{date}.xls')
    # print("Документ сохранен")
