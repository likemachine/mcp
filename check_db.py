from getpass import getpass

import psycopg

password = getpass("Пароль пользователя mcp: ")

try:
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="mcp",
        user="mcp",
        password=password,
        connect_timeout=5,
    ) as conn:
        row = conn.execute(
            "SELECT current_database(), current_user, version()"
        ).fetchone()

    print("Подключение: OK")
    print("База:", row[0])
    print("Пользователь:", row[1])
    print("Версия:", row[2])
except psycopg.Error as exc:
    print("Подключение: ОШИБКА")
    print(str(exc))
