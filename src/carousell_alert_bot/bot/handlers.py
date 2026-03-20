from __future__ import annotations

from collections.abc import Iterable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from carousell_alert_bot.bot.keyboards import (
    cancel_keyboard,
    dashboard_keyboard,
    watch_actions_keyboard,
)
from carousell_alert_bot.bot.states import AddWatchStates, EditWatchStates
from carousell_alert_bot.config import Settings
from carousell_alert_bot.db.models import User, Watch
from carousell_alert_bot.services.watch_service import (
    TelegramIdentity,
    WatchService,
    WatchValidationError,
)
from carousell_alert_bot.utils import format_sgd


async def register_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the dashboard"),
            BotCommand(command="add", description="Create a watch"),
            BotCommand(command="list", description="List your watches"),
            BotCommand(command="pause", description="Pause a watch by ID prefix"),
            BotCommand(command="resume", description="Resume a watch by ID prefix"),
            BotCommand(command="delete", description="Delete a watch by ID prefix"),
            BotCommand(command="cadence", description="Set watch cadence: /cadence <id> <minutes>"),
            BotCommand(command="style", description="Set alert style: /style <id> <text>"),
            BotCommand(command="cancel", description="Cancel the current flow"),
        ]
    )


def _watch_ref(watch: Watch) -> str:
    return watch.id.split("-")[0]


def _render_watch_lines(watches: Iterable[Watch]) -> str:
    lines: list[str] = []
    for watch in watches:
        status = watch.status.value.upper()
        lines.append(
            "\n".join(
                [
                    f"<b>{watch.query}</b> (`{_watch_ref(watch)}`)",
                    f"Status: {status}",
                    f"Max price: {format_sgd(watch.max_price_cents)}",
                    f"Cadence: {watch.cadence_minutes} min",
                    f"Style: {watch.alert_style}",
                    f"Last error: {watch.last_scan_error or 'None'}",
                ]
            )
        )
    return "\n\n".join(lines) if lines else "You do not have any active watches yet."


def build_router(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router()

    def _message_identity(message: Message) -> TelegramIdentity | None:
        if message.from_user is None:
            return None
        return TelegramIdentity(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

    def _callback_identity(callback: CallbackQuery) -> TelegramIdentity:
        return TelegramIdentity(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )

    async def _ensure_user(
        session: AsyncSession,
        identity: TelegramIdentity | None,
        *,
        mark_onboarded: bool = False,
    ) -> User | None:
        if identity is None:
            return None
        service = WatchService(session, settings)
        return await service.ensure_allowed_user(identity, mark_onboarded=mark_onboarded)

    async def _authorize_message(
        message: Message,
        session: AsyncSession,
        *,
        onboard: bool = False,
    ) -> User | None:
        identity = _message_identity(message)
        if identity is None:
            await message.answer("Telegram user metadata is missing.")
            return None
        user = await _ensure_user(session, identity, mark_onboarded=onboard)
        if user is None:
            await message.answer("This bot is allowlist-only right now. Ask an admin to add you.")
        return user

    async def _authorize_callback(
        callback: CallbackQuery,
        session: AsyncSession,
    ) -> User | None:
        user = await _ensure_user(session, _callback_identity(callback))
        if user is None:
            await callback.answer("You are not on the allowlist.", show_alert=True)
        return user

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        async with session_factory() as session:
            user = await _authorize_message(message, session, onboard=True)
            if user is None:
                return
        await message.answer(
            "Use this bot to track Carousell Singapore listings and get immediate deal alerts.",
            reply_markup=dashboard_keyboard(),
        )

    @router.message(Command("add"))
    async def add_handler(message: Message, state: FSMContext) -> None:
        async with session_factory() as session:
            user = await _authorize_message(message, session)
            if user is None:
                return
        await state.set_state(AddWatchStates.query)
        await state.update_data()
        await message.answer("What item should I search for?", reply_markup=cancel_keyboard())

    @router.message(Command("list"))
    async def list_handler(message: Message) -> None:
        async with session_factory() as session:
            user = await _authorize_message(message, session)
            if user is None:
                return
            watches = await WatchService(session, settings).list_watches(user)
        if not watches:
            await message.answer(
                "You do not have any active watches yet.",
                reply_markup=dashboard_keyboard(),
            )
            return
        await message.answer(_render_watch_lines(watches))
        for watch in watches:
            await message.answer(
                f"Manage <b>{watch.query}</b> (`{_watch_ref(watch)}`)",
                reply_markup=watch_actions_keyboard(watch),
            )

    async def _update_watch_with_reference(
        message: Message,
        action: str,
        reference: str,
        value: str | None = None,
        identity: TelegramIdentity | None = None,
    ) -> None:
        async with session_factory() as session:
            user = await _ensure_user(session, identity or _message_identity(message))
            if user is None:
                await message.answer(
                    "This bot is allowlist-only right now. Ask an admin to add you."
                )
                return
            service = WatchService(session, settings)
            try:
                if action == "pause":
                    watch = await service.pause_watch(user=user, reference=reference)
                    text = f"Paused <b>{watch.query}</b>."
                elif action == "resume":
                    watch = await service.resume_watch(user=user, reference=reference)
                    text = f"Resumed <b>{watch.query}</b>."
                elif action == "delete":
                    watch = await service.delete_watch(user=user, reference=reference)
                    text = f"Deleted <b>{watch.query}</b>."
                elif action == "cadence":
                    watch = await service.update_cadence(
                        user=user,
                        reference=reference,
                        cadence_raw=value or "",
                    )
                    text = (
                        f"Updated cadence for <b>{watch.query}</b> "
                        f"to {watch.cadence_minutes} minutes."
                    )
                elif action == "style":
                    watch = await service.update_style(
                        user=user,
                        reference=reference,
                        alert_style=value or "",
                    )
                    text = f"Updated alert style for <b>{watch.query}</b>."
                else:
                    raise WatchValidationError("Unsupported action.")
            except WatchValidationError as exc:
                await message.answer(str(exc))
                return
        await message.answer(text, reply_markup=dashboard_keyboard())

    @router.message(Command("pause"))
    async def pause_handler(message: Message) -> None:
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Usage: /pause <watch_id_prefix>")
            return
        await _update_watch_with_reference(message, "pause", parts[1])

    @router.message(Command("resume"))
    async def resume_handler(message: Message) -> None:
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Usage: /resume <watch_id_prefix>")
            return
        await _update_watch_with_reference(message, "resume", parts[1])

    @router.message(Command("delete"))
    async def delete_handler(message: Message) -> None:
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Usage: /delete <watch_id_prefix>")
            return
        await _update_watch_with_reference(message, "delete", parts[1])

    @router.message(Command("cadence"))
    async def cadence_handler(message: Message) -> None:
        parts = message.text.split(maxsplit=2) if message.text else []
        if len(parts) < 3:
            await message.answer("Usage: /cadence <watch_id_prefix> <minutes>")
            return
        await _update_watch_with_reference(message, "cadence", parts[1], parts[2])

    @router.message(Command("style"))
    async def style_handler(message: Message) -> None:
        parts = message.text.split(maxsplit=2) if message.text else []
        if len(parts) < 3:
            await message.answer("Usage: /style <watch_id_prefix> <natural language preference>")
            return
        await _update_watch_with_reference(message, "style", parts[1], parts[2])

    @router.message(Command("cancel"))
    async def cancel_handler(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Cancelled.", reply_markup=dashboard_keyboard())

    @router.message(AddWatchStates.query)
    async def add_query_handler(message: Message, state: FSMContext) -> None:
        await state.update_data(query=message.text or "")
        await state.set_state(AddWatchStates.max_price)
        await message.answer(
            "What is the maximum listing price in SGD?",
            reply_markup=cancel_keyboard(),
        )

    @router.message(AddWatchStates.max_price)
    async def add_max_price_handler(message: Message, state: FSMContext) -> None:
        await state.update_data(max_price=message.text or "")
        await state.set_state(AddWatchStates.cadence)
        await message.answer(
            f"How often should I scan? Enter minutes between {settings.min_watch_cadence_minutes} "
            f"and {settings.max_watch_cadence_minutes}.",
            reply_markup=cancel_keyboard(),
        )

    @router.message(AddWatchStates.cadence)
    async def add_cadence_handler(message: Message, state: FSMContext) -> None:
        await state.update_data(cadence=message.text or "")
        await state.set_state(AddWatchStates.alert_style)
        await message.answer(
            "How strict should alerts be? Example: 'Only alert for exceptional deals.'",
            reply_markup=cancel_keyboard(),
        )

    @router.message(AddWatchStates.alert_style)
    async def add_style_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        async with session_factory() as session:
            user = await _authorize_message(message, session)
            if user is None:
                return
            service = WatchService(session, settings)
            try:
                watch = await service.create_watch(
                    user=user,
                    query=data.get("query", ""),
                    max_price_raw=data.get("max_price", ""),
                    cadence_raw=data.get("cadence", ""),
                    alert_style=message.text or "",
                )
            except WatchValidationError as exc:
                await message.answer(str(exc), reply_markup=cancel_keyboard())
                return
        await state.clear()
        await message.answer(
            f"Created watch <b>{watch.query}</b> (`{_watch_ref(watch)}`) with a max price of "
            f"{format_sgd(watch.max_price_cents)}.",
            reply_markup=dashboard_keyboard(),
        )

    @router.callback_query(F.data == "watch:add")
    async def add_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with session_factory() as session:
            user = await _authorize_callback(callback, session)
            if user is None:
                return
        await state.set_state(AddWatchStates.query)
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "What item should I search for?",
                reply_markup=cancel_keyboard(),
            )

    @router.callback_query(F.data == "watch:list")
    async def list_callback_handler(callback: CallbackQuery) -> None:
        async with session_factory() as session:
            user = await _authorize_callback(callback, session)
            if user is None:
                return
            watches = await WatchService(session, settings).list_watches(user)
        await callback.answer()
        if callback.message is None:
            return
        if not watches:
            await callback.message.answer(
                "You do not have any active watches yet.",
                reply_markup=dashboard_keyboard(),
            )
            return
        await callback.message.answer(_render_watch_lines(watches))
        for watch in watches:
            await callback.message.answer(
                f"Manage <b>{watch.query}</b> (`{_watch_ref(watch)}`)",
                reply_markup=watch_actions_keyboard(watch),
            )

    @router.callback_query(F.data == "flow:cancel")
    async def flow_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer("Cancelled")
        if callback.message:
            await callback.message.answer("Cancelled.", reply_markup=dashboard_keyboard())

    @router.callback_query(F.data.startswith("watch:"))
    async def watch_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
        message = callback.message
        if message is None:
            await callback.answer()
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 3:
            await callback.answer("Invalid action.", show_alert=True)
            return
        _, action, watch_id = parts

        async with session_factory() as session:
            user = await _authorize_callback(callback, session)
            if user is None:
                return
            service = WatchService(session, settings)
            try:
                watch = await service.resolve_watch(user=user, reference=watch_id)
            except WatchValidationError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

        if action == "cadence":
            await state.set_state(EditWatchStates.cadence)
            await state.update_data(watch_id=watch.id)
            await callback.answer()
            await message.answer(
                f"Send the new cadence in minutes for <b>{watch.query}</b>.",
                reply_markup=cancel_keyboard(),
            )
            return
        if action == "style":
            await state.set_state(EditWatchStates.style)
            await state.update_data(watch_id=watch.id)
            await callback.answer()
            await message.answer(
                f"Send the new alert style for <b>{watch.query}</b>.",
                reply_markup=cancel_keyboard(),
            )
            return

        await callback.answer()
        await _update_watch_with_reference(
            message,
            action,
            watch.id,
            identity=_callback_identity(callback),
        )

    @router.message(EditWatchStates.cadence)
    async def edit_cadence_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        watch_id = data.get("watch_id")
        if not watch_id:
            await state.clear()
            await message.answer("No watch selected.", reply_markup=dashboard_keyboard())
            return
        await _update_watch_with_reference(
            message,
            "cadence",
            watch_id,
            message.text or "",
        )
        await state.clear()

    @router.message(EditWatchStates.style)
    async def edit_style_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        watch_id = data.get("watch_id")
        if not watch_id:
            await state.clear()
            await message.answer("No watch selected.", reply_markup=dashboard_keyboard())
            return
        await _update_watch_with_reference(
            message,
            "style",
            watch_id,
            message.text or "",
        )
        await state.clear()

    return router
