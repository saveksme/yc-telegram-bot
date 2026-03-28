from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from yandex.cloud.compute.v1.instance_pb2 import Instance

if TYPE_CHECKING:
    from aiogram import Bot

    from app.services.accounts import AccountManager
    from app.services.yandex_cloud import YandexCloudService

logger = logging.getLogger(__name__)

JOB_ID = "autostart_watchdog"
STATE_FILE = Path("/app/data/autostart.json")


class AutoStartWatchdog:
    """Checks all VMs every 60s; if a VM is STOPPED it gets started automatically.

    The feature can be toggled on/off per-account from the bot UI.
    Enabled account IDs are persisted to disk so they survive restarts.
    """

    def __init__(
        self,
        yc_service: YandexCloudService,
        account_manager: AccountManager,
        bot: Bot,
        notify_user_ids: list[int],
    ) -> None:
        self._yc = yc_service
        self._accounts = account_manager
        self._bot = bot
        self._notify_ids = notify_user_ids
        self._enabled: set[str] = set()
        self._load()

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._check_job,
            IntervalTrigger(seconds=60),
            id=JOB_ID,
            replace_existing=True,
        )

    # ── persistence ───────────────────────────────────────────────
    def _load(self) -> None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self._enabled = set(data)
            except Exception:
                logger.exception("Failed to load autostart state")

    def _save(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(list(self._enabled), ensure_ascii=False), encoding="utf-8"
        )

    # ── public API ────────────────────────────────────────────────
    def is_enabled(self, account_id: str) -> bool:
        return account_id in self._enabled

    def enable(self, account_id: str) -> None:
        self._enabled.add(account_id)
        self._save()
        logger.info("AutoStart enabled for account %s", account_id)

    def disable(self, account_id: str) -> None:
        self._enabled.discard(account_id)
        self._save()
        logger.info("AutoStart disabled for account %s", account_id)

    def remove_account(self, account_id: str) -> None:
        self._enabled.discard(account_id)
        self._save()

    # ── watchdog job ──────────────────────────────────────────────
    async def _check_job(self) -> None:
        for acc in self._accounts:
            if acc.id not in self._enabled:
                continue

            try:
                vms = await self._yc.list_vms(acc)
            except Exception:
                logger.exception("[%s] AutoStart: failed to list VMs", acc.name)
                continue

            for vm in vms:
                if vm.status != Instance.Status.STOPPED:
                    continue

                vm_name = vm.name or vm.id
                logger.info("[%s] AutoStart: starting VM %s", acc.name, vm_name)
                try:
                    await self._yc.start_vm(acc, vm.id)
                    text = f"\U0001f7e2 <b>AutoStart</b>: VM <b>{vm_name}</b> [{acc.name}] was stopped — started automatically."
                except Exception:
                    logger.exception("[%s] AutoStart: failed to start VM %s", acc.name, vm_name)
                    text = f"\u274c <b>AutoStart</b>: failed to start <b>{vm_name}</b> [{acc.name}]"

                for uid in self._notify_ids:
                    try:
                        await self._bot.send_message(uid, text, parse_mode="HTML")
                    except Exception:
                        logger.exception("Failed to notify user %s", uid)

    # ── lifecycle ─────────────────────────────────────────────────
    def start(self) -> None:
        self._scheduler.start()
        logger.info("AutoStart watchdog started (checking every 60s)")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("AutoStart watchdog stopped")
