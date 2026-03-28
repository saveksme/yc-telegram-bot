# YC Telegram Bot

Telegram-бот для управления виртуальными машинами в Yandex Cloud. Позволяет запускать, останавливать и перезагружать VM прямо из Telegram, а также автоматически поднимать упавшие машины.

## Возможности

- **Мульти-аккаунт** — подключение нескольких аккаунтов Yandex Cloud с разными OAuth-токенами и каталогами
- **Управление VM** — просмотр списка виртуальных машин, статуса, характеристик (vCPU, RAM, IP-адреса, зона)
- **Действия** — запуск, остановка и перезагрузка VM в один клик через inline-кнопки
- **AutoStart** — watchdog, который каждые 60 секунд проверяет состояние VM и автоматически запускает остановленные машины (включается/выключается по аккаунтам)
- **Уведомления** — бот сообщает в Telegram, когда AutoStart поднимает VM или не может это сделать
- **Авторизация** — доступ ограничен списком разрешённых Telegram user ID

## Стек

- Python 3.11+
- [aiogram 3](https://docs.aiogram.dev/) — Telegram Bot API
- [Yandex Cloud SDK](https://github.com/yandex-cloud/python-sdk) — управление инфраструктурой через gRPC
- [APScheduler](https://apscheduler.readthedocs.io/) — планировщик для AutoStart watchdog
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — конфигурация из `.env`
- Docker / Docker Compose

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/saveksme/yc-telegram-bot.git
cd yc-telegram-bot
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактировать `.env`:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `ALLOWED_TELEGRAM_USER_IDS` | Список разрешённых Telegram user ID через запятую |
| `LOG_LEVEL` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### 3. Запустить

**Docker Compose (рекомендуется):**

```bash
docker compose up -d
```

**Локально:**

```bash
pip install -r requirements.txt
python -m app
```

## Использование

1. Отправить `/start` боту в Telegram
2. Перейти в **Accounts** и добавить аккаунт Yandex Cloud (имя, OAuth-токен, Folder ID)
3. Перейти в **My VMs** — выбрать аккаунт и увидеть список виртуальных машин
4. Нажать на VM для просмотра статуса и управления (Start / Stop / Restart)
5. В разделе **AutoStart** включить автоматический запуск для нужных аккаунтов

## Структура проекта

```
├── app/
│   ├── __main__.py          # Точка входа
│   ├── bot.py               # Инициализация бота и диспетчера
│   ├── config.py            # Конфигурация (pydantic-settings)
│   ├── handlers/
│   │   └── vm.py            # Хендлеры команд и callback-кнопок
│   ├── middlewares/
│   │   └── auth.py          # Middleware авторизации по user ID
│   ├── services/
│   │   ├── accounts.py      # Менеджер аккаунтов (JSON-хранилище)
│   │   ├── scheduler.py     # AutoStart watchdog (APScheduler)
│   │   └── yandex_cloud.py  # Клиент Yandex Cloud Compute API
│   └── utils/
│       └── formatting.py    # Форматирование статусов VM
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Получение OAuth-токена Yandex Cloud

1. Перейти по ссылке: https://oauth.yandex.ru/authorize?response_type=token&client_id=1a6990aa636648e9b2ef855fa7bec2fb
2. Авторизоваться и скопировать полученный токен
3. Ввести токен при добавлении аккаунта в боте

## Лицензия

[GPL-3.0](LICENSE)
