#!/usr/bin/env python3
# bot.py
# Telegram bot that downloads (low-res) videos using yt-dlp and sends them to chat.
# Supports browser-exported cookies via env var YTDLP_COOKIES_CONTENT (written to YTDLP_COOKIES_FILE).
import os
import re
import asyncio
import logging
from yt_dlp import YoutubeDL, DownloadError
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config from env ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("Please set TELEGRAM_TOKEN environment variable")

# Cookie support: write YTDLP_COOKIES_CONTENT -> file path YTDLP_COOKIES_FILE at startup
YTDLP_COOKIES_CONTENT = os.environ.get("YTDLP_COOKIES_CONTENT")  # multiline cookies.txt content (DO NOT COMMIT)
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "/tmp/cookies.txt")

# Bot upload limits
TG_SIZE_LIMIT = 50 * 1024 * 1024   # 50 MB
CHUNK_SIZE = 48 * 1024 * 1024     # 48 MB chunk parts
TMP_DIR = "/tmp"
URL_RE = re.compile(r'(https?://\S+)')

def ensure_cookies_file():
    """If YTDLP_COOKIES_CONTENT is provided, write it to YTDLP_COOKIES_FILE."""
    if YTDLP_COOKIES_CONTENT:
        try:
            os.makedirs(os.path.dirname(YTDLP_COOKIES_FILE), exist_ok=True)
        except Exception:
            pass
        with open(YTDLP_COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(YTDLP_COOKIES_CONTENT)
        logger.info("Wrote cookies to %s", YTDLP_COOKIES_FILE)
    else:
        logger.info("No YTDLP_COOKIES_CONTENT provided; proceeding without cookies")

def download_with_ytdlp(url: str, outdir: str = TMP_DIR) -> str:
    """Blocking download using yt-dlp. Returns filepath."""
    ydl_opts = {
        'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]/best[height<=360]/best',
        'outtmpl': os.path.join(outdir, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'no_warnings': True,
        'quiet': True,
        'merge_output_format': 'mp4',
        'geo_bypass': True,
        'retries': 3,
        'skip_unavailable_fragments': True,
    }

    # If cookie file exists, set it
    if os.path.exists(YTDLP_COOKIES_FILE):
        ydl_opts['cookiefile'] = YTDLP_COOKIES_FILE
        logger.info("Using cookiefile: %s", YTDLP_COOKIES_FILE)

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except DownloadError as e:
            raise RuntimeError(f"yt-dlp DownloadError: {e}")
        filename = ydl.prepare_filename(info)
        # prefer .mp4 if merged
        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            mp4 = base + '.mp4'
            if os.path.exists(mp4):
                filename = mp4
        # fallback: try find by id
        if not os.path.exists(filename):
            vid_id = info.get('id')
            for fname in os.listdir(outdir):
                if fname.startswith(vid_id + '.'):
                    cand = os.path.join(outdir, fname)
                    if os.path.getsize(cand) > 0:
                        filename = cand
                        break
        if not os.path.exists(filename):
            raise RuntimeError("Download completed but output file not found")
        return filename

def split_file(path: str, chunk_size: int = CHUNK_SIZE):
    parts = []
    with open(path, 'rb') as f:
        idx = 1
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part_path = f"{path}.part{idx:03d}"
            with open(part_path, 'wb') as pf:
                pf.write(chunk)
            parts.append(part_path)
            idx += 1
    return parts

# Telegram handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a YouTube URL or use /dl <URL>\nI try to download a low-res copy (<=360p) and send it here.\nIf content requires login/age-check, set YTDLP_COOKIES_CONTENT env (cookies.txt content)."
    )

async def dl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        url = context.args[0]
    else:
        await update.message.reply_text("Usage: /dl <URL>")
        return
    await handle_download(update, context, url)

async def text_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    m = URL_RE.search(text)
    if not m:
        return
    url = m.group(1)
    await handle_download(update, context, url)

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    chat_id = update.effective_chat.id
    status = await update.message.reply_text(f"Queued: {url}\nStarting download...")
    try:
        loop = asyncio.get_running_loop()
        filepath = await loop.run_in_executor(None, download_with_ytdlp, url)
    except Exception as e:
        logger.exception("Download failed")
        msg = str(e)
        extra = ""
        if 'age-restricted' in msg.lower() or 'login' in msg.lower() or 'private' in msg.lower():
            extra = ("\n\nHint: This video may require login/cookies. "
                     "Set YTDLP_COOKIES_CONTENT (exported cookies.txt content) in env and restart.")
        await status.edit_text(f"❌ Download failed: {e}{extra}")
        return

    try:
        size = os.path.getsize(filepath)
    except Exception as e:
        logger.exception("Could not get filesize")
        await status.edit_text(f"Downloaded but failed to access file: {e}")
        return

    if size <= TG_SIZE_LIMIT:
        await status.edit_text(f"Uploading {os.path.basename(filepath)} ({size//1024//1024} MB)...")
        try:
            with open(filepath, 'rb') as f:
                await context.bot.send_document(chat_id, document=f, filename=os.path.basename(filepath))
        except Exception as e:
            logger.exception("Upload failed")
            await status.edit_text(f"Upload failed: {e}")
            return
        finally:
            try:
                os.remove(filepath)
            except:
                pass
        await status.edit_text("✅ Done — file sent.")
        return

    # split and send parts
    await status.edit_text(f"File is {size//1024//1024} MB (>50MB). Splitting into parts...")
    try:
        parts = await asyncio.get_running_loop().run_in_executor(None, split_file, filepath)
        for p in parts:
            with open(p, 'rb') as fh:
                await context.bot.send_document(chat_id, document=fh, filename=os.path.basename(p))
            try:
                os.remove(p)
            except:
                pass
        try:
            os.remove(filepath)
        except:
            pass
        await status.edit_text("✅ Done — big file sent in parts.")
    except Exception as e:
        logger.exception("Splitting/upload failed")
        await status.edit_text(f"Failed to split/upload parts: {e}")

def main():
    # ensure cookies file present if content provided
    ensure_cookies_file()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('dl', dl_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), text_url_handler))
    logger.info("Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
