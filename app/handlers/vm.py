from __future__ import annotations

import logging

from html import escape as html_escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.accounts import AccountManager
from app.services.scheduler import AutoStartWatchdog
from app.services.yandex_cloud import YandexCloudService
from app.utils.formatting import format_vm_list, format_vm_status

router = Router()
logger = logging.getLogger(__name__)


# ── FSM states for adding an account ──────────────────────────────
class AddAccount(StatesGroup):
    name = State()
    token = State()
    folder = State()


# ── Keyboard builders ─────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f5a5 My VMs", callback_data="pick_account")],
        [InlineKeyboardButton(text="\U0001f4cb Accounts", callback_data="accounts")],
        [InlineKeyboardButton(text="\U0001f6e1 AutoStart", callback_data="autostart")],
    ])


def accounts_kb(accounts: AccountManager) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"\U0001f4c1 {acc.name}",
            callback_data=f"acc_info:{acc.id}",
        )]
        for acc in accounts
    ]
    rows.append([InlineKeyboardButton(text="\u2795 Add account", callback_data="acc_add")])
    rows.append([InlineKeyboardButton(text="\u25c0 Back", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_info_kb(account_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u274c Remove account", callback_data=f"acc_rm:{account_id}")],
        [InlineKeyboardButton(text="\u25c0 Back", callback_data="accounts")],
    ])


def pick_account_kb(accounts: AccountManager) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"\U0001f4c1 {acc.name}",
            callback_data=f"vms:{acc.id}",
        )]
        for acc in accounts
    ]
    rows.append([InlineKeyboardButton(text="\u25c0 Back", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vm_list_kb(account_id: str, vms) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{vm.name}",
            callback_data=f"vm:{account_id}:{vm.id}",
        )]
        for vm in vms
    ]
    rows.append([InlineKeyboardButton(text="\u25c0 Back", callback_data="pick_account")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vm_actions_kb(account_id: str, vm_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u25b6 Start", callback_data=f"act:start:{account_id}:{vm_id}"),
            InlineKeyboardButton(text="\u23f9 Stop", callback_data=f"act:stop:{account_id}:{vm_id}"),
        ],
        [
            InlineKeyboardButton(text="\U0001f504 Restart", callback_data=f"act:restart:{account_id}:{vm_id}"),
            InlineKeyboardButton(text="\U0001f504 Refresh", callback_data=f"vm:{account_id}:{vm_id}"),
        ],
        [InlineKeyboardButton(text="\u25c0 Back", callback_data=f"vms:{account_id}")],
    ])


def autostart_kb(accounts: AccountManager, watchdog: AutoStartWatchdog) -> InlineKeyboardMarkup:
    rows = []
    for acc in accounts:
        enabled = watchdog.is_enabled(acc.id)
        icon = "\U0001f7e2" if enabled else "\U0001f534"
        label = f"{icon} {acc.name}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"as_toggle:{acc.id}",
        )])
    rows.append([InlineKeyboardButton(text="\u25c0 Back", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0 Main menu", callback_data="main")],
    ])


# ── /start ────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Yandex Cloud VM Manager</b>\n\nChoose an action:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


# ── Main menu callback ───────────────────────────────────────────
@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "<b>Yandex Cloud VM Manager</b>\n\nChoose an action:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ── Accounts list ─────────────────────────────────────────────────
@router.callback_query(F.data == "accounts")
async def cb_accounts(call: CallbackQuery, account_manager: AccountManager) -> None:
    accs = account_manager.list_all()
    text = f"<b>Accounts ({len(accs)})</b>" if accs else "<b>No accounts added yet.</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=accounts_kb(account_manager))
    await call.answer()


@router.callback_query(F.data.startswith("acc_info:"))
async def cb_account_info(call: CallbackQuery, account_manager: AccountManager) -> None:
    acc_id = call.data.split(":")[1]
    acc = account_manager.get(acc_id)
    if not acc:
        await call.answer("Account not found", show_alert=True)
        return
    text = (
        f"<b>{acc.name}</b>\n"
        f"Folder ID: <code>{acc.folder_id}</code>\n"
        f"Token: <code>{acc.oauth_token[:8]}...{acc.oauth_token[-4:]}</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=account_info_kb(acc_id))
    await call.answer()


@router.callback_query(F.data.startswith("acc_rm:"))
async def cb_account_remove(
    call: CallbackQuery, account_manager: AccountManager,
    yc_service: YandexCloudService, watchdog: AutoStartWatchdog,
) -> None:
    acc_id = call.data.split(":")[1]
    acc = account_manager.get(acc_id)
    name = acc.name if acc else acc_id
    account_manager.remove(acc_id)
    yc_service.drop_cache(acc_id)
    watchdog.remove_account(acc_id)
    await call.answer(f"Account '{name}' removed", show_alert=True)
    accs = account_manager.list_all()
    text = f"<b>Accounts ({len(accs)})</b>" if accs else "<b>No accounts added yet.</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=accounts_kb(account_manager))


# ── Add account FSM ───────────────────────────────────────────────
@router.callback_query(F.data == "acc_add")
async def cb_add_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddAccount.name)
    await call.message.edit_text(
        "<b>New account</b>\n\nEnter a name for this account:",
        parse_mode="HTML",
        reply_markup=back_main_kb(),
    )
    await call.answer()


@router.message(AddAccount.name)
async def fsm_acc_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Enter <b>OAuth token</b> for Yandex Cloud:",
        parse_mode="HTML",
        reply_markup=back_main_kb(),
    )
    await state.set_state(AddAccount.token)


@router.message(AddAccount.token)
async def fsm_acc_token(message: Message, state: FSMContext) -> None:
    await state.update_data(token=message.text.strip())
    await message.answer(
        "Enter <b>Folder ID</b>:",
        parse_mode="HTML",
        reply_markup=back_main_kb(),
    )
    await state.set_state(AddAccount.folder)


@router.message(AddAccount.folder)
async def fsm_acc_folder(message: Message, state: FSMContext, account_manager: AccountManager) -> None:
    data = await state.get_data()
    acc = account_manager.add(
        name=data["name"],
        oauth_token=data["token"],
        folder_id=message.text.strip(),
    )
    await state.clear()
    await message.answer(
        f"Account <b>{acc.name}</b> added!",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


# ── Pick account → VM list ────────────────────────────────────────
@router.callback_query(F.data == "pick_account")
async def cb_pick_account(call: CallbackQuery, account_manager: AccountManager) -> None:
    if not account_manager.list_all():
        await call.answer("Add an account first!", show_alert=True)
        return
    await call.message.edit_text(
        "<b>Select account:</b>",
        parse_mode="HTML",
        reply_markup=pick_account_kb(account_manager),
    )
    await call.answer()


@router.callback_query(F.data.startswith("vms:"))
async def cb_vm_list(
    call: CallbackQuery, account_manager: AccountManager, yc_service: YandexCloudService
) -> None:
    acc_id = call.data.split(":")[1]
    acc = account_manager.get(acc_id)
    if not acc:
        await call.answer("Account not found", show_alert=True)
        return

    await call.answer("Loading VMs...")
    try:
        vms = await yc_service.list_vms(acc)
    except Exception as e:
        logger.exception("Failed to list VMs for %s", acc.name)
        await call.message.edit_text(
            f"Failed to load VMs: {html_escape(str(e))}",
            parse_mode="HTML",
            reply_markup=back_main_kb(),
        )
        return

    text = f"<b>{acc.name}</b>\n\n{format_vm_list(vms)}"
    await call.message.edit_text(
        text, parse_mode="HTML", reply_markup=vm_list_kb(acc_id, vms)
    )


# ── Single VM status ──────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^vm:[^:]+:[^:]+$"))
async def cb_vm_status(
    call: CallbackQuery, account_manager: AccountManager, yc_service: YandexCloudService
) -> None:
    _, acc_id, vm_id = call.data.split(":")
    acc = account_manager.get(acc_id)
    if not acc:
        await call.answer("Account not found", show_alert=True)
        return

    await call.answer("Loading...")
    try:
        vm = await yc_service.get_vm(acc, vm_id)
    except Exception as e:
        logger.exception("Failed to get VM %s", vm_id)
        await call.message.edit_text(
            f"Error: {html_escape(str(e))}", parse_mode="HTML", reply_markup=back_main_kb()
        )
        return

    await call.message.edit_text(
        format_vm_status(vm),
        parse_mode="HTML",
        reply_markup=vm_actions_kb(acc_id, vm_id),
    )


# ── VM actions (start / stop / restart) ───────────────────────────
@router.callback_query(F.data.startswith("act:"))
async def cb_vm_action(
    call: CallbackQuery, account_manager: AccountManager, yc_service: YandexCloudService
) -> None:
    parts = call.data.split(":")
    action, acc_id, vm_id = parts[1], parts[2], parts[3]
    acc = account_manager.get(acc_id)
    if not acc:
        await call.answer("Account not found", show_alert=True)
        return

    action_labels = {"start": "Starting", "stop": "Stopping", "restart": "Restarting"}
    await call.message.edit_text(
        f"\u23f3 {action_labels[action]} VM...",
        parse_mode="HTML",
    )
    await call.answer()

    try:
        if action == "start":
            await yc_service.start_vm(acc, vm_id)
        elif action == "stop":
            await yc_service.stop_vm(acc, vm_id)
        elif action == "restart":
            await yc_service.restart_vm(acc, vm_id)

        vm = await yc_service.get_vm(acc, vm_id)
        await call.message.edit_text(
            f"\u2705 Done!\n\n{format_vm_status(vm)}",
            parse_mode="HTML",
            reply_markup=vm_actions_kb(acc_id, vm_id),
        )
    except Exception as e:
        logger.exception("Action %s failed on VM %s", action, vm_id)
        await call.message.edit_text(
            f"\u274c Failed: {html_escape(str(e))}",
            parse_mode="HTML",
            reply_markup=vm_actions_kb(acc_id, vm_id),
        )


# ── AutoStart ─────────────────────────────────────────────────────
@router.callback_query(F.data == "autostart")
async def cb_autostart(
    call: CallbackQuery, account_manager: AccountManager, watchdog: AutoStartWatchdog
) -> None:
    accs = account_manager.list_all()
    if not accs:
        await call.answer("Add an account first!", show_alert=True)
        return

    await call.message.edit_text(
        "<b>\U0001f6e1 AutoStart</b>\n\n"
        "When enabled, stopped VMs are automatically started (checked every 60s).\n\n"
        "Tap an account to toggle:",
        parse_mode="HTML",
        reply_markup=autostart_kb(account_manager, watchdog),
    )
    await call.answer()


@router.callback_query(F.data.startswith("as_toggle:"))
async def cb_autostart_toggle(
    call: CallbackQuery, account_manager: AccountManager, watchdog: AutoStartWatchdog
) -> None:
    acc_id = call.data.split(":")[1]
    acc = account_manager.get(acc_id)
    if not acc:
        await call.answer("Account not found", show_alert=True)
        return

    if watchdog.is_enabled(acc_id):
        watchdog.disable(acc_id)
        await call.answer(f"AutoStart disabled for {acc.name}")
    else:
        watchdog.enable(acc_id)
        await call.answer(f"AutoStart enabled for {acc.name}")

    await call.message.edit_text(
        "<b>\U0001f6e1 AutoStart</b>\n\n"
        "When enabled, stopped VMs are automatically started (checked every 60s).\n\n"
        "Tap an account to toggle:",
        parse_mode="HTML",
        reply_markup=autostart_kb(account_manager, watchdog),
    )
