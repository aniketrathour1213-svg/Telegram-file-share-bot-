"""
Telegram File Sharing & Monetization Bot
Built with Pyrogram + FastAPI — production-ready for Render Web Service.

Features:
    - Admin file upload with unique deep-link generation
    - Dual-channel force-join verification
    - Monetization-ready link workflow
    - File tracking (views/downloads)
    - Admin analytics dashboard
    - Auto-start database initialization
"""

import asyncio
import logging
import sys
import os
import random
import string
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.errors import (
    FloodWait,
    UserNotParticipant,
    ChatAdminRequired,
    RPCError,
)

from config import Config
from database import (
    init_db,
    add_or_update_user,
    save_file,
    get_file_by_unique_id,
    get_file_by_file_id,
    get_all_files,
    get_total_files,
    get_total_users,
    get_total_downloads,
    get_total_views,
    get_total_links,
    get_detailed_stats,
    record_download,
    record_view,
    get_views_by_file,
    get_all_users,
)

# ═══════════════════════════════════════════════════════════════════════
# Logging Configuration
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress noisy library logs
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("PyroClient").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# ═══════════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════════

fastapi_app = FastAPI(title="Telegram File Sharing Bot")

# ═══════════════════════════════════════════════════════════════════════
# Pyrogram Client (global, set during startup)
# ═══════════════════════════════════════════════════════════════════════

bot: Optional[Client] = None

# ═══════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════


def generate_unique_id(length: int = 10) -> str:
    """Generate a random alphanumeric unique ID for file links."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


async def is_admin(user_id: int) -> bool:
    """Check if the user is the configured admin."""
    return user_id == Config.ADMIN_ID


async def check_membership(client: Client, user_id: int) -> bool:
    """
    Check if a user is a member of both required channels.
    Returns True only if the user is currently a member of both.
    """
    channels = [
        (Config.CHANNEL_1_ID, Config.CHANNEL_1_NAME),
        (Config.CHANNEL_2_ID, Config.CHANNEL_2_NAME),
    ]

    for channel_id, channel_name in channels:
        try:
            member = await client.get_chat_member(
                chat_id=channel_id, user_id=user_id
            )
            if member.status in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
            ):
                logger.info(
                    f"User {user_id} is {member.status} in {channel_name}"
                )
                return False
            # RESTRICTED but still a member — allow
        except UserNotParticipant:
            logger.info(
                f"User {user_id} is not a participant in {channel_name}"
            )
            return False
        except (ChatAdminRequired, RPCError) as e:
            logger.error(
                f"Bot lacks permissions for {channel_name}: {e}"
            )
            # If bot can't verify, allow access (fail open)
            continue
        except Exception as e:
            logger.error(
                f"Unexpected error checking {channel_name}: {e}"
            )
            continue

    return True


def get_force_join_keyboard() -> InlineKeyboardMarkup:
    """Build the force-join inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Config.CHANNEL_1_NAME,
                    url=Config.CHANNEL_1_LINK,
                ),
                InlineKeyboardButton(
                    text=Config.CHANNEL_2_NAME,
                    url=Config.CHANNEL_2_LINK,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ I Have Joined All Channels",
                    callback_data="verify_join",
                ),
            ],
        ]
    )


async def send_file_to_user(
    client: Client, user_id: int, file_data: dict, reply_msg: Message
):
    """
    Send the stored file to a user and append the copyright notice
    as a separate message (never as a media caption).
    """
    file_id = file_data["file_id"]
    file_type = file_data["file_type"]
    caption = file_data.get("caption") or ""
    file_name = file_data.get("file_name") or "file"

    # Record the view and download
    user = reply_msg.from_user
    record_view(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        file_id=file_id,
    )
    record_download(user_id=user_id, file_id=file_id)

    try:
        kwargs = {"chat_id": user_id, "caption": caption or None}

        if file_type == "video":
            await client.send_video(
                chat_id=user_id, video=file_id, caption=caption or None
            )
        elif file_type == "audio":
            await client.send_audio(
                chat_id=user_id, audio=file_id, caption=caption or None
            )
        elif file_type == "photo":
            await client.send_photo(
                chat_id=user_id, photo=file_id, caption=caption or None
            )
        elif file_type == "voice":
            await client.send_voice(
                chat_id=user_id, voice=file_id, caption=caption or None
            )
        elif file_type == "animation":
            await client.send_animation(
                chat_id=user_id,
                animation=file_id,
                caption=caption or None,
            )
        elif file_type == "video_note":
            await client.send_video_note(
                chat_id=user_id, video_note=file_id
            )
        elif file_type == "sticker":
            await client.send_sticker(chat_id=user_id, sticker=file_id)
        else:
            # Default: send as document
            await client.send_document(
                chat_id=user_id,
                document=file_id,
                caption=caption or None,
            )

        # ── Separate copyright notice (never attached as caption) ──
        await client.send_message(
            chat_id=user_id,
            text=(
                "<b>⚠️ IMPORTANT NOTE</b>\n\n"
                "Please save or forward this video immediately.\n\n"
                "<i>This video may be removed within 30 minutes "
                "due to copyright reasons.</i>"
            ),
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )

        logger.info(f"File delivered to user {user_id} [{file_id[:16]}…]")

    except FloodWait as e:
        logger.warning(f"FloodWait: sleeping {e.value}s")
        await asyncio.sleep(e.value)
        # One retry
        await send_file_to_user(client, user_id, file_data, reply_msg)
    except Exception as e:
        logger.error(
            f"Error sending file {file_id[:16]}→{user_id}: {e}"
        )
        try:
            await reply_msg.reply_text(
                "❌ Failed to send the file. Please try again later."
            )
        except Exception:
            pass


async def handle_deep_link(
    client: Client, message: Message, unique_id: str
):
    """
    Handle /start UNIQUE_ID deep-link workflow.
    1. Track the user.
    2. Verify the file exists.
    3. Check force-join membership.
    4. Deliver the file or show the force-join prompt.
    """
    user = message.from_user
    user_id = user.id

    # Track user
    add_or_update_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
    )

    # Verify file exists
    file_data = get_file_by_unique_id(unique_id)
    if not file_data:
        await message.reply_text(
            "❌ <b>Invalid or expired link.</b>\n\n"
            "The file you are looking for does not exist "
            "or has been removed.",
            parse_mode=enums.ParseMode.HTML,
        )
        return

    # Check force-join
    is_member = await check_membership(client, user_id)
    if not is_member:
        await message.reply_text(
            "🔒 <b>Channel Subscription Required</b>\n\n"
            "Before accessing this content, you must join "
            "the following channels.",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=get_force_join_keyboard(),
        )
        # The file will be delivered after callback verification
        return

    # Already a member — send the file directly
    logger.info(
        f"Direct access: user {user_id} → file {unique_id}"
    )
    await send_file_to_user(client, user_id, file_data, message)


# ═══════════════════════════════════════════════════════════════════════
# Pyrogram Message Handlers
# ═══════════════════════════════════════════════════════════════════════

# We attach decorators to the global 'client' after it is created.
# Since the client is created inside main(), we store handlers here
# and register them manually using add_handler().

from pyrogram.handlers import (
    MessageHandler,
    CallbackQueryHandler,
)


async def start_command(client: Client, message: Message):
    """Handle /start — plain or with deep-link payload."""
    text = message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) > 1:
        # Deep-link: /start UNIQUE_ID
        unique_id = parts[1].strip()
        await handle_deep_link(client, message, unique_id)
        return

    # Plain /start
    user = message.from_user
    add_or_update_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    if await is_admin(user.id):
        await message.reply_text(
            "👋 <b>Welcome Admin!</b>\n\n"
            "Send me any file/video to generate a unique "
            "sharing link.\n\n"
            "Available commands:\n"
            "• <code>/stats</code> — View bot statistics\n"
            "• <code>/admin</code> — Admin dashboard\n"
            "• <code>/views FILE_ID</code> — View access log\n"
            "• <code>/files</code> — List all uploaded files\n"
            "• <code>/broadcast</code> — Message all users\n\n"
            "<i>Just send any file to get started!</i>",
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "👋 <b>Welcome!</b>\n\n"
            "This bot provides access to shared files via "
            "unique links.\n"
            "Please use the link provided by the content creator.",
            parse_mode=enums.ParseMode.HTML,
        )


async def file_upload(client: Client, message: Message):
    """Handle file uploads — admin only."""
    user_id = message.from_user.id

    if not await is_admin(user_id):
        await message.reply_text(
            "❌ You are not authorized to upload files.",
            quote=True,
        )
        return

    # ── Extract file metadata ──
    file_id = None
    file_type = None
    file_name = None
    file_size = None
    mime_type = None
    caption = message.caption or ""

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
        file_name = message.video.file_name or (
            f"video_{message.video.file_unique_id}"
        )
        file_size = message.video.file_size
        mime_type = message.video.mime_type
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name or (
            f"doc_{message.document.file_unique_id}"
        )
        file_size = message.document.file_size
        mime_type = message.document.mime_type
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
        file_name = message.audio.file_name or (
            f"audio_{message.audio.file_unique_id}"
        )
        file_size = message.audio.file_size
        mime_type = message.audio.mime_type
    elif message.photo:
        # Use the largest photo size
        file_id = message.photo.file_id
        file_type = "photo"
        file_name = f"photo_{message.photo.file_unique_id}.jpg"
        file_size = message.photo.file_size
        mime_type = "image/jpeg"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"
        file_name = f"voice_{message.voice.file_unique_id}.ogg"
        file_size = message.voice.file_size
        mime_type = message.voice.mime_type
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "animation"
        file_name = message.animation.file_name or (
            f"anim_{message.animation.file_unique_id}"
        )
        file_size = message.animation.file_size
        mime_type = message.animation.mime_type
    elif message.video_note:
        file_id = message.video_note.file_id
        file_type = "video_note"
        file_name = f"videonote_{message.video_note.file_unique_id}"
        file_size = message.video_note.file_size
        mime_type = "video/mp4"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_type = "sticker"
        file_name = f"sticker_{message.sticker.file_unique_id}"
        file_size = 0
        mime_type = "image/webp"
    else:
        await message.reply_text(
            "❌ Unsupported file type. Please send a video, "
            "document, audio, or photo.",
            quote=True,
        )
        return

    if not file_id:
        await message.reply_text(
            "❌ Could not extract file. Please try again.",
            quote=True,
        )
        return

    # ── Generate unique ID ──
    unique_id = generate_unique_id()
    while get_file_by_unique_id(unique_id):
        unique_id = generate_unique_id()

    # ── Save to database ──
    success = save_file(
        file_id=file_id,
        unique_id=unique_id,
        file_type=file_type,
        file_name=file_name,
        file_size=file_size,
        caption=caption,
        mime_type=mime_type,
    )

    if not success:
        await message.reply_text(
            "❌ Failed to save file. Please try again.",
            quote=True,
        )
        return

    # ── Build deep link ──
    bot_username = Config.BOT_USERNAME
    if not bot_username:
        bot_self = await client.get_me()
        bot_username = bot_self.username
        Config.BOT_USERNAME = bot_username

    deep_link = f"https://t.me/{bot_username}?start={unique_id}"

    # Format file size
    size_str = ""
    if file_size:
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

    file_type_display = file_type.replace("_", " ").title()

    await message.reply_text(
        f"✅ <b>File Uploaded Successfully!</b>\n\n"
        f"📄 <b>Name:</b> <code>{file_name}</code>\n"
        f"📁 <b>Type:</b> {file_type_display}\n"
        f"📏 <b>Size:</b> {size_str}\n"
        f"🔗 <b>Unique ID:</b> <code>{unique_id}</code>\n\n"
        f"⬇️ <b>Share Link:</b>\n"
        f"<code>{deep_link}</code>\n\n"
        f"📊 Use <code>/views {file_id}</code> to track access.",
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="📋 Copy Share Link",
                        url=f"https://t.me/share/url?url={deep_link}",
                    )
                ]
            ]
        ),
    )

    logger.info(f"Admin uploaded: {file_name} → {unique_id}")


async def stats_command(client: Client, message: Message):
    """Handle /stats — show bot statistics (admin only)."""
    if not await is_admin(message.from_user.id):
        await message.reply_text(
            "❌ You are not authorized to use this command."
        )
        return

    stats = get_detailed_stats()
    await message.reply_text(
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> <code>{stats['total_users']}</code>\n"
        f"📁 <b>Total Files:</b> <code>{stats['total_files']}</code>\n"
        f"🔗 <b>Total Links:</b> <code>{stats['total_links']}</code>\n"
        f"⬇️ <b>Total Downloads:</b> "
        f"<code>{stats['total_downloads']}</code>\n"
        f"👁️ <b>Total Views:</b> "
        f"<code>{stats['total_views']}</code>\n\n"
        "Use <code>/admin</code> for detailed dashboard.",
        parse_mode=enums.ParseMode.HTML,
    )


async def admin_command(client: Client, message: Message):
    """Handle /admin — detailed dashboard (admin only)."""
    if not await is_admin(message.from_user.id):
        await message.reply_text(
            "❌ You are not authorized to use this command."
        )
        return

    stats = get_detailed_stats()

    top_text = ""
    if stats["top_files"]:
        top_text = "<b>Top Files:</b>\n"
        for i, f in enumerate(stats["top_files"][:5], 1):
            name = (
                (f["file_name"][:30] + "…")
                if len(f["file_name"]) > 30
                else f["file_name"]
            )
            top_text += (
                f"{i}. <code>{name}</code>\n"
                f"   👁️ {f['views']} views | "
                f"⬇️ {f['downloads']} downloads\n"
            )

    dashboard = (
        "📊 <b>Admin Dashboard</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Users:</b> <code>{stats['total_users']}</code>\n"
        f"📁 <b>Files:</b> <code>{stats['total_files']}</code>\n"
        f"🔗 <b>Links:</b> <code>{stats['total_links']}</code>\n"
        f"⬇️ <b>Downloads:</b> "
        f"<code>{stats['total_downloads']}</code>\n"
        f"👁️ <b>Views:</b> <code>{stats['total_views']}</code>\n\n"
    )

    if top_text:
        dashboard += (
            "━━━━━━━━━━━━━━━━━━━\n" + top_text + "\n"
        )

    dashboard += (
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Commands:</b>\n"
        "• <code>/stats</code> — Quick stats\n"
        "• <code>/views FILE_ID</code> — View access log\n"
        "• <code>/files</code> — List all files\n"
        "• <code>/broadcast</code> — Send to all users"
    )

    await message.reply_text(dashboard, parse_mode=enums.ParseMode.HTML)


async def views_command(client: Client, message: Message):
    """Handle /views FILE_ID — show who viewed a file (admin only)."""
    if not await is_admin(message.from_user.id):
        await message.reply_text(
            "❌ You are not authorized to use this command."
        )
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text(
            "❌ Usage: <code>/views FILE_ID</code>\n\n"
            "Get the FILE_ID from the upload confirmation message.",
            parse_mode=enums.ParseMode.HTML,
        )
        return

    file_id = parts[1].strip()
    file_data = get_file_by_file_id(file_id)
    if not file_data:
        await message.reply_text("❌ File not found in database.")
        return

    views = get_views_by_file(file_id)
    file_name = file_data.get("file_name") or "Unnamed"
    total_views = len(views)

    text = (
        f"📄 <b>File:</b> <code>{file_name}</code>\n"
        f"👁️ <b>Total Views:</b> <code>{total_views}</code>\n\n"
    )

    if total_views == 0:
        text += "No one has viewed this file yet."
    else:
        text += "<b>Viewers:</b>\n"
        for i, view in enumerate(views[:20], 1):
            uname = view.get("username") or "—"
            fname = view.get("first_name") or "Unknown"
            ts = view.get("viewed_at", "")
            try:
                ts = (
                    datetime.fromisoformat(ts).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                )
            except (ValueError, TypeError):
                pass
            text += f"{i}. {fname} (@{uname}) — {ts}\n"

        if total_views > 20:
            text += f"\n… and {total_views - 20} more viewers."

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


async def files_command(client: Client, message: Message):
    """Handle /files — list all uploaded files (admin only)."""
    if not await is_admin(message.from_user.id):
        await message.reply_text(
            "❌ You are not authorized to use this command."
        )
        return

    files = get_all_files()
    if not files:
        await message.reply_text("📁 No files uploaded yet.")
        return

    text = f"📁 <b>Uploaded Files ({len(files)})</b>\n\n"
    for i, f in enumerate(files[:20], 1):
        name = (
            (f.get("file_name") or "Unnamed")[:40]
        )
        ftype = (
            f.get("file_type", "unknown")
            .replace("_", " ")
            .title()
        )
        views = len(get_views_by_file(f["file_id"]))
        text += (
            f"{i}. <code>{name}</code>\n"
            f"   [{ftype}] 👁️ {views} views | "
            f"ID: <code>{f['file_id'][:15]}…</code>\n\n"
        )

    if len(files) > 20:
        text += f"\n… and {len(files) - 20} more files."

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


async def broadcast_command(client: Client, message: Message):
    """Handle /broadcast — send a message to all users (admin only)."""
    if not await is_admin(message.from_user.id):
        await message.reply_text(
            "❌ You are not authorized to use this command."
        )
        return

    # Get broadcast text
    broadcast_text = None
    if message.reply_to_message:
        broadcast_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
        )
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            broadcast_text = parts[1]

    if not broadcast_text:
        await message.reply_text(
            "❌ Usage: <code>/broadcast Your message here</code>\n\n"
            "Or reply to a message with <code>/broadcast</code>",
            parse_mode=enums.ParseMode.HTML,
        )
        return

    await message.reply_text(
        "📢 Broadcasting message to all users…\n"
        "This may take a while."
    )

    users = get_all_users()
    success = 0
    failed = 0

    for user in users:
        try:
            await client.send_message(
                chat_id=user["user_id"],
                text=broadcast_text,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
            )
            success += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            logger.warning(
                f"FloodWait broadcast: sleeping {e.value}s"
            )
            await asyncio.sleep(e.value)
            try:
                await client.send_message(
                    chat_id=user["user_id"],
                    text=broadcast_text,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

    await message.reply_text(
        f"📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Sent: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>\n"
        f"👥 Total: <code>{len(users)}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle inline callback queries — primarily force-join verification."""
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "verify_join":
        is_member = await check_membership(client, user_id)

        if not is_member:
            try:
                await callback_query.answer(
                    "❌ You have not joined all channels yet!",
                    show_alert=True,
                )
            except Exception:
                pass
            return

        # Membership verified
        try:
            await callback_query.answer(
                "✅ Membership verified!",
                show_alert=False,
            )
        except Exception:
            pass

        # Update the force-join message
        try:
            await callback_query.message.edit_text(
                "✅ <b>Membership Verified!</b>\n\n"
                "Please click your original file link again "
                "to access the content.",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

        # Search recent chat history for a pending /start with file ID
        try:
            async for msg in client.get_chat_history(
                chat_id=user_id, limit=15
            ):
                if (
                    msg.text
                    and msg.text.startswith("/start ")
                    and len(msg.text) > 7
                ):
                    potential_id = msg.text.split("/start ", 1)[
                        1
                    ].strip()
                    if potential_id and get_file_by_unique_id(
                        potential_id
                    ):
                        file_data = get_file_by_unique_id(potential_id)
                        await send_file_to_user(
                            client, user_id, file_data, callback_query.message
                        )
                        return
        except Exception as e:
            logger.error(
                f"Error finding pending file for {user_id}: {e}"
            )

        # Fallback
        try:
            await callback_query.message.reply_text(
                "ℹ️ Please use your original file link again — "
                "it will work now that you've joined the channels."
            )
        except Exception:
            pass

    else:
        try:
            await callback_query.answer(
                "❌ Invalid request.", show_alert=True
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# Register Handlers
# ═══════════════════════════════════════════════════════════════════════


def register_handlers(client: Client):
    """Register all message and callback query handlers."""
    client.add_handler(
        MessageHandler(start_command, filters.command("start")),
    )
    client.add_handler(
        MessageHandler(
            file_upload,
            (
                filters.video
                | filters.document
                | filters.audio
                | filters.photo
                | filters.voice
                | filters.animation
                | filters.video_note
                | filters.sticker
            ),
        ),
    )
    client.add_handler(
        MessageHandler(stats_command, filters.command("stats")),
    )
    client.add_handler(
        MessageHandler(admin_command, filters.command("admin")),
    )
    client.add_handler(
        MessageHandler(views_command, filters.command("views")),
    )
    client.add_handler(
        MessageHandler(files_command, filters.command("files")),
    )
    client.add_handler(
        MessageHandler(
            broadcast_command, filters.command("broadcast")
        ),
    )
    client.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("✅ All handlers registered successfully")


# ═══════════════════════════════════════════════════════════════════════
# FastAPI Routes
# ═══════════════════════════════════════════════════════════════════════


@fastapi_app.get("/")
async def health_check():
    """Health-check endpoint required by Render."""
    return {
        "status": "running",
        "service": "Telegram File Sharing Bot",
        "timestamp": datetime.now().isoformat(),
    }


@fastapi_app.get("/health")
async def health_check_detailed():
    """Detailed health-check with database status."""
    try:
        init_db()
        stats = get_detailed_stats()
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "Telegram File Sharing Bot",
                "database": "connected",
                "stats": {
                    "users": stats["total_users"],
                    "files": stats["total_files"],
                    "views": stats["total_views"],
                },
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )


# ═══════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════


async def run_fastapi():
    """Start the FastAPI / Uvicorn server."""
    config = uvicorn.Config(
        app=fastapi_app,
        host=Config.HOST,
        port=Config.PORT,
        log_level="info",
        use_colors=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot():
    """Start the Pyrogram bot client and keep it alive."""
    global bot

    Config.validate()
    init_db()

    bot = Client(
        name="file_sharing_bot",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        sleep_threshold=60,
        max_concurrent_transmissions=3,
        workdir="./",
    )

    register_handlers(bot)

    await bot.start()

    # Fetch bot username
    bot_self = await bot.get_me()
    Config.BOT_USERNAME = bot_self.username

    logger.info(
        f"✅ Bot started: @{bot_self.username} (ID: {bot_self.id})"
    )
    logger.info(
        f"📢 Force-join: {Config.CHANNEL_1_NAME} "
        f"({Config.CHANNEL_1_ID})"
    )
    logger.info(
        f"📢 Force-join: {Config.CHANNEL_2_NAME} "
        f"({Config.CHANNEL_2_ID})"
    )
    logger.info(f"👑 Admin user ID: {Config.ADMIN_ID}")
    logger.info(
        f"🌐 FastAPI health-check on 0.0.0.0:{Config.PORT}"
    )

    # Keep running until stopped
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await bot.stop()
        logger.info("🛑 Bot stopped")


async def main():
    """Run FastAPI and Pyrogram concurrently."""
    logger.info("🚀 Starting Telegram File Sharing & Monetization Bot")

    try:
        await asyncio.gather(run_fastapi(), run_bot())
    except asyncio.CancelledError:
        logger.info("🛑 Tasks cancelled — shutting down")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)
