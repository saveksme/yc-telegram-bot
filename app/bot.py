from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers.vm import router as vm_router
from app.middlewares.auth import AuthMiddleware
from app.services.accounts import AccountManager
from app.services.scheduler import AutoStartWatchdog
from app.services.yandex_cloud import YandexCloudService


async def main() -> None:
    config = Settings()

    logging.basicConfig(
        level=config.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(token=config.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    account_manager = AccountManager()
    yc_service = YandexCloudService()
    watchdog = AutoStartWatchdog(
        yc_service=yc_service,
        account_manager=account_manager,
        bot=bot,
        notify_user_ids=config.allowed_telegram_user_ids,
    )

    dp.update.outer_middleware(AuthMiddleware(config.allowed_telegram_user_ids))
    dp.include_router(vm_router)

    dp["yc_service"] = yc_service
    dp["account_manager"] = account_manager
    dp["watchdog"] = watchdog

    async def on_startup() -> None:
        watchdog.start()

    async def on_shutdown() -> None:
        watchdog.stop()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)
