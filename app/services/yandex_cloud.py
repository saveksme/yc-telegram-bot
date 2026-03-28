from __future__ import annotations

import asyncio
import logging

import grpc
import yandexcloud
from yandex.cloud.compute.v1.instance_pb2 import Instance
from yandex.cloud.compute.v1.instance_service_pb2 import (
    GetInstanceRequest,
    ListInstancesRequest,
    StartInstanceRequest,
    StopInstanceRequest,
)
from yandex.cloud.compute.v1.instance_service_pb2_grpc import InstanceServiceStub

from app.services.accounts import Account

logger = logging.getLogger(__name__)


class YandexCloudService:
    """Creates SDK connections per-account on demand."""

    def __init__(self) -> None:
        self._sdks: dict[str, tuple[yandexcloud.SDK, InstanceServiceStub]] = {}

    def _get_client(self, account: Account) -> tuple[yandexcloud.SDK, InstanceServiceStub]:
        if account.id not in self._sdks:
            sdk = yandexcloud.SDK(token=account.oauth_token)
            stub = sdk.client(InstanceServiceStub)
            self._sdks[account.id] = (sdk, stub)
        return self._sdks[account.id]

    def drop_cache(self, account_id: str) -> None:
        self._sdks.pop(account_id, None)

    async def list_vms(self, account: Account) -> list[Instance]:
        sdk, stub = self._get_client(account)
        response = await asyncio.to_thread(
            stub.List,
            ListInstancesRequest(folder_id=account.folder_id),
        )
        return list(response.instances)

    async def get_vm(self, account: Account, instance_id: str) -> Instance:
        _, stub = self._get_client(account)
        return await asyncio.to_thread(
            stub.Get,
            GetInstanceRequest(instance_id=instance_id),
        )

    async def _wait_until_ready(self, account: Account, instance_id: str, max_wait: int = 120) -> None:
        """Poll VM status until it is RUNNING or STOPPED (not transitional)."""
        transitional = {
            Instance.Status.STARTING,
            Instance.Status.STOPPING,
            Instance.Status.PROVISIONING,
        }
        for _ in range(max_wait // 5):
            vm = await self.get_vm(account, instance_id)
            if vm.status not in transitional:
                return
            await asyncio.sleep(5)

    async def start_vm(self, account: Account, instance_id: str) -> None:
        await self._wait_until_ready(account, instance_id)
        sdk, stub = self._get_client(account)
        operation = await asyncio.to_thread(
            stub.Start,
            StartInstanceRequest(instance_id=instance_id),
        )
        await asyncio.to_thread(
            sdk.wait_operation_and_get_result, operation, timeout=300
        )
        logger.info("[%s] VM %s started", account.name, instance_id)

    async def stop_vm(self, account: Account, instance_id: str) -> None:
        await self._wait_until_ready(account, instance_id)
        sdk, stub = self._get_client(account)
        operation = await asyncio.to_thread(
            stub.Stop,
            StopInstanceRequest(instance_id=instance_id),
        )
        await asyncio.to_thread(
            sdk.wait_operation_and_get_result, operation, timeout=300
        )
        logger.info("[%s] VM %s stopped", account.name, instance_id)

    async def restart_vm(self, account: Account, instance_id: str) -> None:
        logger.info("[%s] Restarting VM %s ...", account.name, instance_id)
        await self.stop_vm(account, instance_id)
        await self.start_vm(account, instance_id)

    async def restart_all_vms(self, account: Account) -> list[str]:
        vms = await self.list_vms(account)
        restarted: list[str] = []
        for vm in vms:
            if vm.status == Instance.Status.RUNNING:
                try:
                    await self.restart_vm(account, vm.id)
                    restarted.append(vm.name or vm.id)
                except Exception:
                    logger.exception(
                        "[%s] Failed to restart VM %s", account.name, vm.name or vm.id
                    )
        return restarted

    async def find_vm(self, account: Account, query: str) -> Instance | None:
        vms = await self.list_vms(account)
        for vm in vms:
            if vm.id == query or vm.name == query:
                return vm
        return None
