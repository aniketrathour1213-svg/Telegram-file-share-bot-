# Telegram File Sharing & Monetization Bot

A production-ready Telegram bot that generates unique shareable links for files with **dual-channel force-join verification** and **monetization-ready deep links**.

## Features

- ✅ **Admin File Upload** — Upload any file/video/audio/photo and get a unique share link
- 🔗 **Deep Link Generation** — Creates `https://t.me/BOT_USERNAME?start=UNIQUE_ID` links
- 🔒 **Dual-Channel Force Join** — Users must join both channels before receiving files
- 💰 **Monetization Ready** — Links work seamlessly with external monetization services
- 📊 **Analytics Dashboard** — Track views, downloads, users, and popular files
- 👁️ **View Tracking** — See exactly who viewed each file and when
- 📦 **All File Types** — Video, document, audio, photo, voice, animation, stickers

## Quick Start

### 1. Prerequisites

- Python 3.9+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- API_ID and API_HASH from [my.telegram.org](https://my.telegram.org)
- A [Render](https://render.com) account (for deployment)

### 2. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram bot token from BotFather |
| `API_ID` | ✅ | API ID from my.telegram.org |
| `API_HASH` | ✅ | API Hash from my.telegram.org |
| `ADMIN_ID` | ✅ | `6501901607` |
| `CHANNEL_1_ID` | ✅ | `-1004295662200` |
| `CHANNEL_2_ID` | ✅ | `-1004297747395` |
| `CHANNEL_1_LINK` | ✅ | `https://t.me/+awB_9F3KdV82ZWZl` |
| `CHANNEL_2_LINK` | ✅ | `https://t.me/+EDVjhWCNhTk0MDBl` |
| `DATABASE_URL` | ❌ | Custom SQLite path (default: `file_sharing_bot.db`) |
| `PORT` | ❌ | Render assigns this automatically (`10000`) |

### 3. Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/file-sharing-bot
cd file-sharing-bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export BOT_TOKEN="your_bot_token"
export API_ID="your_api_id"
export API_HASH="your_api_hash"
export ADMIN_ID="6501901607"
export CHANNEL_1_ID="-1004295662200"
export CHANNEL_2_ID="-1004297747395"
export CHANNEL_1_LINK="https://t.me/+awB_9F3KdV82ZWZl"
export CHANNEL_2_LINK="https://t.me/+EDVjhWCNhTk0MDBl"

# Run the bot
python main.py
