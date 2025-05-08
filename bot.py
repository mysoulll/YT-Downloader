import os
import re
import logging
from typing import Dict
from pytube import YouTube
from moviepy.editor import VideoFileClip
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatAction
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes
)

# Konfigurasi untuk Railway
PORT = int(os.environ.get('PORT', 5000))
TOKEN = os.environ.get('TELEGRAM_TOKEN')  # Diambil dari env variables
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Direktori temporary (Railway menggunakan ephemeral storage)
TEMP_DIR = "/tmp/yt_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Ikon untuk UI
ICONS = {
    'welcome': '🎬✨',
    'success': '✅🎉',
    'error': '❌⚠️',
    'download': '⏬📥',
    'converting': '🔄🎧'
}

# State management
user_state: Dict[int, Dict] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /start"""
    welcome_msg = (
        f"{ICONS['welcome']} *YouTube Downloader*\n\n"
        "Saya bisa mengunduh video YouTube dan mengkonversinya ke MP3/MP4.\n\n"
        "🔹 *Cara menggunakan*:\n"
        "1. Kirim /download\n"
        "2. Tempel link YouTube\n"
        "3. Pilih format\n\n"
        "⚠️ *Catatan*:\n"
        "- Bot ini hanya untuk video <50MB\n"
        "- Hasil download bersifat sementara"
    )
    
    buttons = [
        [InlineKeyboardButton("📥 Download", callback_data='download')]
    ]
    
    await update.message.reply_text(
        welcome_msg,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode='Markdown'
    )

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses permintaan download"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"{ICONS['download']} Kirim link YouTube yang ingin diunduh\n\n"
        "Contoh: https://youtu.be/example",
        parse_mode='Markdown'
    )
    user_state[update.effective_user.id] = {"waiting_for": "url"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses pesan berisi URL"""
    user_id = update.effective_user.id
    
    if user_id in user_state and user_state[user_id].get("waiting_for") == "url":
        url = update.message.text
        
        if not re.match(r'^(https?://)?(www\.)?(youtube|youtu)\.', url):
            await update.message.reply_text(
                f"{ICONS['error']} URL tidak valid!",
                parse_mode='Markdown'
            )
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
                f"📌 *{user_state[user_id]['title']}*\n"
                "Pilih format:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text(
                f"{ICONS['error']} Gagal memproses video",
                parse_mode='Markdown'
            )

async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses download berdasarkan pilihan"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_state:
        await query.edit_message_text(f"{ICONS['error']} Sesi expired!")
        return
    
    format_type = query.data
    url = user_state[user_id]["url"]
    
    try:
        await query.edit_message_text(f"{ICONS['download']} Memulai download...")
        yt = YouTube(url)
        
        if format_type == 'mp3':
            await download_mp3(update, context, yt)
        else:
            await download_mp4(update, context, yt)
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text(f"{ICONS['error']} Gagal mengunduh!")

async def download_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    """Download dan konversi ke MP3"""
    chat_id = update.effective_chat.id
    
    try:
        # Download video
        video_path = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first().download(
            output_path=TEMP_DIR,
            filename_prefix="temp_"
        )
        
        # Convert to MP3
        mp3_path = os.path.join(TEMP_DIR, "audio.mp3")
        video_clip = VideoFileClip(video_path)
        audio_clip = video_clip.audio
        audio_clip.write_audiofile(mp3_path)
        audio_clip.close()
        video_clip.close()
        
        # Kirim file
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
        with open(mp3_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=yt.title[:30],
                performer=yt.author
            )
        
        # Bersihkan file
        os.remove(video_path)
        os.remove(mp3_path)
        
        await context.bot.send_message(
            chat_id,
            f"{ICONS['success']} Berhasil diunduh sebagai MP3!"
        )
        
    except Exception as e:
        logger.error(f"MP3 error: {e}")
        raise

async def download_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    """Download sebagai MP4"""
    chat_id = update.effective_chat.id
    
    try:
        video = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first()
        
        video_path = video.download(
            output_path=TEMP_DIR,
            filename="video.mp4"
        )
        
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=yt.title[:30]
            )
        
        os.remove(video_path)
        await context.bot.send_message(
            chat_id,
            f"{ICONS['success']} Berhasil diunduh sebagai MP4!"
        )
        
    except Exception as e:
        logger.error(f"MP4 error: {e}")
        raise

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error("Exception:", exc_info=context.error)
    if update.message:
        await update.message.reply_text(
            f"{ICONS['error']} Terjadi error. Coba lagi nanti.",
            parse_mode='Markdown'
        )

def main():
    """Start the bot"""
    app = Application.builder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handle_download, pattern='^download$'))
    app.add_handler(CallbackQueryHandler(process_download, pattern='^(mp3|mp4)$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    # Deployment configuration
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
