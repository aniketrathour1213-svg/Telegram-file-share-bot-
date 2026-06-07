"""
Configuration Module for Telegram File Sharing & Monetization Bot.
All settings are loaded from environment variables for Render deployment.
"""

import os
import logging

logger = logging.getLogger(__name__)


class Config:
    """Bot configuration loaded from environment variables."""

    # Pyrogram / Telegram API credentials
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")

    # Admin user ID (only this user can upload and manage)
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "6501901607"))

    # Force-join channels
    CHANNEL_1_ID: int = int(os.getenv("CHANNEL_1_ID", "-1004295662200"))
    CHANNEL_2_ID: int = int(os.getenv("CHANNEL_2_ID", "-1004297747395"))
    CHANNEL_1_LINK: str = os.getenv(
        "CHANNEL_1_LINK", "https://t.me/+awB_9F3KdV82ZWZl"
    )
    CHANNEL_2_LINK: str = os.getenv(
        "CHANNEL_2_LINK", "https://t.me/+EDVjhWCNhTk0MDBl"
    )

    CHANNEL_1_NAME: str = "𝐇𝐢𝐧𝐨𝐯𝐢𝐱𝐚"
    CHANNEL_2_NAME: str = "𝐇𝐢𝐧𝐨𝐯𝐢𝐱𝐚 𝐛𝐚𝐜𝐤𝐮𝐩"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "file_sharing_bot.db")

    # Server
    PORT: int = int(os.getenv("PORT", "10000"))
    HOST: str = "0.0.0.0"

    # Bot username (set after client starts)
    BOT_USERNAME: str = ""

    @classmethod
    def validate(cls):
        """Validate that all required config values are set."""
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        if not cls.API_ID or cls.API_ID == 0:
            errors.append("API_ID is required")
        if not cls.API_HASH:
            errors.append("API_HASH is required")
        if errors:
            raise ValueError(
                "Configuration errors: " + "; ".join(errors)
            )
        logger.info("✅ Configuration validated successfully")
