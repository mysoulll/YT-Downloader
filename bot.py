import os
import re
import logging
from typing import Dict
from pytube import YouTube
from moviepy.editor import VideoFileClip
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes
)

# Konfigurasi Railway
PORT = int(os.environ.get('PORT', 5000))
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TEMP_DIR = "/tmp/yt_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

ICONS = {
    'welcome': '🎬✨',
    'success': '✅🎉',
    'error': '❌⚠️',
    'download': '⏬📥',
    'converting': '🔄🎧'
}

user_state: Dict[int, Dict] = {}

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download", callback_data='download')],
        [InlineKeyboardButton("❓ Bantuan", callback_data='help')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"{ICONS['welcome']} *YouTube Downloader*\n\n"
        "Saya dapat membantu mengunduh video dari YouTube sebagai MP3/MP4.\n\n"
        "🔹 *Cara Pakai*:\n"
        "1. Klik Download\n"
        "2. Kirim link YouTube\n"
        "3. Pilih format file\n\n"
        "⚠️ *Catatan*:\n"
        "- Maksimal ukuran file 50MB\n"
        "- File akan dihapus otomatis"
    )
    await update.message.reply_text(msg, reply_markup=main_menu(), parse_mode='Markdown')

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❓ *Bantuan*\n\n"
        "- Kirim link YouTube valid\n"
        "- Pilih format unduhan: MP3 untuk audio atau MP4 untuk video\n\n"
        "Jika ingin kembali, klik tombol di bawah ini.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Kembali ke Beranda", callback_data='home')]
        ])
    )

async def handle_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Kembali ke menu utama.",
        reply_markup=main_menu()
    )

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"{ICONS['download']} Kirim link YouTube yang ingin kamu unduh.\n\nContoh: https://youtu.be/xyz",
        parse_mode='Markdown'
    )
    user_state[update.effective_user.id] = {"waiting_for": "url"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_state and user_state[user_id].get("waiting_for") == "url":
        url = update.message.text
        if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/', url):
            await update.message.reply_text(f"{ICONS['error']} URL tidak valid!")
            return
        try:
            yt = YouTube(url)
            user_state[user_id] = {
                "url": url,
                "title": yt.title[:50] + "..." if len(yt.title) > 50 else yt.title,
                "waiting_for": "format"
            }
            buttons = [
                [InlineKeyboardButton("🎧 MP3", callback_data='mp3'),
                 InlineKeyboardButton("🎥 MP4", callback_data='mp4')]
            ]
            await update.message.reply_text(
                f"📌 *{user_state[user_id]['title']}*\nPilih format:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text(f"{ICONS['error']} Gagal memproses video.")

async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id not in user_state:
        await query.edit_message_text(f"{ICONS['error']} Sesi kadaluarsa!")
        return
    format_type = query.data
    url = user_state[user_id]["url"]
    try:
        await query.edit_message_text(f"{ICONS['download']} Mengunduh video...")
        yt = YouTube(url)
        if format_type == 'mp3':
            await download_mp3(update, context, yt)
        else:
            await download_mp4(update, context, yt)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text(f"{ICONS['error']} Gagal mengunduh!")

async def download_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
    video_path = yt.streams.filter(
        progressive=True,
        file_extension='mp4'
    ).order_by('resolution').desc().first().download(
        output_path=TEMP_DIR,
        filename_prefix="temp_"
    )
    mp3_path = os.path.join(TEMP_DIR, "audio.mp3")
    video_clip = VideoFileClip(video_path)
    audio_clip = video_clip.audio
    audio_clip.write_audiofile(mp3_path)
    audio_clip.close()
    video_clip.close()

    with open(mp3_path, 'rb') as audio_file:
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=audio_file,
            title=yt.title[:30],
            performer=yt.author
        )
    os.remove(video_path)
    os.remove(mp3_path)
    await context.bot.send_message(chat_id, f"{ICONS['success']} Berhasil diunduh sebagai MP3!")

async def download_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
    video = yt.streams.filter(
        progressive=True,
        file_extension='mp4'
    ).order_by('resolution').desc().first()
    video_path = video.download(output_path=TEMP_DIR, filename="video.mp4")

    with open(video_path, 'rb') as video_file:
        await context.bot.send_video(chat_id=chat_id, video=video_file, caption=yt.title[:30])
    os.remove(video_path)
    await context.bot.send_message(chat_id, f"{ICONS['success']} Berhasil diunduh sebagai MP4!")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            f"{ICONS['error']} Terjadi kesalahan. Silakan coba lagi nanti.",
            parse_mode='Markdown'
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handle_download, pattern='^download$'))
    app.add_handler(CallbackQueryHandler(show_help, pattern='^help$'))
    app.add_handler(CallbackQueryHandler(handle_home, pattern='^home$'))
    app.add_handler(CallbackQueryHandler(process_download, pattern='^(mp3|mp4)$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == '__main__':
    main()
