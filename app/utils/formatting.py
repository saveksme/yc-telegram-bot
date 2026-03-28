from __future__ import annotations

from yandex.cloud.compute.v1.instance_pb2 import Instance

_STATUS_EMOJI = {
    "RUNNING": "\U0001f7e2",      # green circle
    "STOPPED": "\U0001f534",      # red circle
    "STARTING": "\U0001f7e1",     # yellow circle
    "STOPPING": "\U0001f7e1",     # yellow circle
    "PROVISIONING": "\U0001f7e0", # orange circle
    "DELETING": "\u26d4",         # no entry
    "ERROR": "\u274c",            # cross mark
}


def _status_name(instance: Instance) -> str:
    return Instance.Status.Name(instance.status)


def status_emoji(status: str) -> str:
    return _STATUS_EMOJI.get(status, "\u2753")


def format_vm_list(instances: list[Instance]) -> str:
    if not instances:
        return "No virtual machines found in the folder."

    lines: list[str] = []
    for vm in instances:
        st = _status_name(vm)
        emoji = status_emoji(st)
        lines.append(f"{emoji} <b>{vm.name}</b> — {st}\n   <code>{vm.id}</code>")
    return "\n".join(lines)


def format_vm_status(vm: Instance) -> str:
    st = _status_name(vm)
    emoji = status_emoji(st)

    zone = vm.zone_id
    platform = vm.platform_id
    cores = vm.resources.cores
    memory_gb = vm.resources.memory / (1024 ** 3)

    # Collect network interfaces
    ips: list[str] = []
    for iface in vm.network_interfaces:
        if iface.primary_v4_address.address:
            ips.append(f"internal: {iface.primary_v4_address.address}")
        if iface.primary_v4_address.one_to_one_nat.address:
            ips.append(f"external: {iface.primary_v4_address.one_to_one_nat.address}")

    parts = [
        f"{emoji} <b>{vm.name}</b>",
        f"ID: <code>{vm.id}</code>",
        f"Status: {st}",
        f"Zone: {zone}",
        f"Platform: {platform}",
        f"vCPU: {cores} | RAM: {memory_gb:.1f} GB",
    ]
    if ips:
        parts.append("Network: " + ", ".join(ips))

    return "\n".join(parts)
