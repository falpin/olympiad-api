bind = "0.0.0.0:8100"  # Или UNIX-сокет: "unix:/tmp/gunicorn.sock"
workers = 4  # Оптимально: (2 * CPU_cores) + 1
worker_class = "sync"  # Или "gthread" / "gevent" для асинхронности
timeout = 30  # Максимальное время выполнения запроса (сек)
keepalive = 2  # Keep-alive соединения (сек)

# Логирование
accesslog = "-"  # '-' — вывод в stdout, или укажите файл ("/var/log/gunicorn/access.log")
errorlog = "-"   # '-' — вывод в stderr, или укажите файл ("/var/log/gunicorn/error.log")
loglevel = "info"

# Безопасность
user = "www-data"  # Пользователь, от которого работает Gunicorn (если запускается от root)
group = "www-data"  # Группа
umask = 0o007  # Права доступа для сокета (если используется UNIX-сокет)

# Переменные среды
raw_env = [
    "FLASK_ENV=production",
]

reload = False  # True — автоматическая перезагрузка при изменении кода (не для production!)