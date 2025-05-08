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
    ContextTypes,
    ConversationHandler
)

# Konfigurasi
TOKEN = os.getenv('TELEGRAM_TOKEN')
PORT = int(os.getenv('PORT', 5000))
TEMP_DIR = "/tmp/yt_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# State conversation
SELECTING_ACTION, PROCESSING_LINK, CHOOSING_FORMAT = range(3)

# Ikon untuk UI
ICONS = {
    'menu': '📱',
    'download': '⏬',
    'success': '✅',
    'error': '❌',
    'audio': '🎧',
    'video': '🎥',
    'loading': '⏳'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu utama"""
    await show_main_menu(update, context)
    return SELECTING_ACTION

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu utama dengan tombol interaktif"""
    menu_text = (
        f"{ICONS['menu']} *YouTube Downloader*\n\n"
        "Pilih aksi yang ingin dilakukan:"
    )
    
    buttons = [
        [InlineKeyboardButton(f"{ICONS['download']} Download", callback_data='download')],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data='help')]
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='Markdown'
        )
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='Markdown'
        )

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses permintaan download"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"{ICONS['download']} Silakan kirim link YouTube yang ingin diunduh:\n\n"
        "Contoh: https://youtu.be/contoh",
        parse_mode='Markdown'
    )
    return PROCESSING_LINK

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses link YouTube yang diterima"""
    url = update.message.text
    user_id = update.effective_user.id
    
    # Validasi URL
    if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/', url):
        await update.message.reply_text(
            f"{ICONS['error']} URL YouTube tidak valid!",
            parse_mode='Markdown'
        )
        await show_main_menu(update, context)
        return SELECTING_ACTION
    
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        # Dapatkan info video
        yt = YouTube(url)
        context.user_data['yt'] = {
            'url': url,
            'title': yt.title,
            'author': yt.author,
            'length': yt.length
        }
        
        # Tampilkan pilihan format
        buttons = [
            [
                InlineKeyboardButton(f"{ICONS['audio']} MP3 (Audio)", callback_data='mp3'),
                InlineKeyboardButton(f"{ICONS['video']} MP4 (Video)", callback_data='mp4')
            ],
            [InlineKeyboardButton("⬅️ Kembali", callback_data='cancel')]
        ]
        
        duration = f"{yt.length // 60}:{yt.length % 60:02d}"
        await update.message.reply_text(
            f"📌 *{yt.title[:60]}*\n"
            f"👤 {yt.author} | ⏱ {duration}\n\n"
            "Pilih format yang diinginkan:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='Markdown'
        )
        
        return CHOOSING_FORMAT
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            f"{ICONS['error']} Gagal memproses video. Pastikan link benar dan coba lagi.",
            parse_mode='Markdown'
        )
        await show_main_menu(update, context)
        return SELECTING_ACTION

async def process_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memproses pilihan format"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel':
        await show_main_menu(update, context)
        return SELECTING_ACTION
    
    format_type = query.data
    yt_info = context.user_data['yt']
    
    try:
        await query.edit_message_text(
            f"{ICONS['loading']} Memulai proses download {format_type.upper()}...",
            parse_mode='Markdown'
        )
        
        yt = YouTube(yt_info['url'])
        
        if format_type == 'mp3':
            await download_mp3(update, context, yt)
        else:
            await download_mp4(update, context, yt)
            
        await show_main_menu(update, context)
        return SELECTING_ACTION
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text(
            f"{ICONS['error']} Gagal mengunduh {format_type.upper()}",
            parse_mode='Markdown'
        )
        await show_main_menu(update, context)
        return SELECTING_ACTION

async def download_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    """Download dan konversi ke MP3"""
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
        
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
        with open(mp3_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=yt.title[:30],
                performer=yt.author,
                duration=yt.length
            )
        
        # Bersihkan file
        os.remove(video_path)
        os.remove(mp3_path)
        
        await context.bot.send_message(
            chat_id,
            f"{ICONS['success']} Berhasil diunduh sebagai MP3!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"MP3 error: {e}")
        raise

async def download_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE, yt: YouTube):
    """Download sebagai MP4"""
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        
        video = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first()
        
        video_path = video.download(
            output_path=TEMP_DIR,
            filename="video.mp4"
        )
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=yt.title[:60],
                supports_streaming=True
            )
        
        os.remove(video_path)
        await context.bot.send_message(
            chat_id,
            f"{ICONS['success']} Berhasil diunduh sebagai MP4!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"MP4 error: {e}")
        raise

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pesan bantuan"""
    help_text = (
        f"{ICONS['menu']} *Bantuan YouTube Downloader*\n\n"
        "🔹 Cara menggunakan:\n"
        "1. Pilih menu Download\n"
        "2. Kirim link video YouTube\n"
        "3. Pilih format (MP3/MP4)\n"
        "4. Tunggu proses selesai\n\n"
        "⚠️ Catatan:\n"
        "- Maksimal ukuran video 50MB\n"
        "- Hasil download bersifat sementara\n\n"
        "🔗 Contoh link yang valid:\n"
        "https://youtu.be/contoh\n"
        "https://www.youtube.com/watch?v=contoh"
    )
    
    buttons = [
        [InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data='menu')]
    ]
    
    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan operasi dan kembali ke menu"""
    await show_main_menu(update, context)
    return SELECTING_ACTION

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Menangani error"""
    logger.error("Exception:", exc_info=context.error)
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            f"{ICONS['error']} Terjadi kesalahan. Silakan coba lagi.",
            parse_mode='Markdown'
        )
        await show_main_menu(update, context)
    
    return SELECTING_ACTION

def main():
    """Menjalankan bot"""
    app = Application.builder().token(TOKEN).build()
    
    # Setup ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(handle_download, pattern='^download$'),
                CallbackQueryHandler(help_command, pattern='^help$'),
                CallbackQueryHandler(start, pattern='^menu$')
            ],
            PROCESSING_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ],
            CHOOSING_FORMAT: [
                CallbackQueryHandler(process_format_selection, pattern='^(mp3|mp4)$'),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)
    
    # Jalankan bot
    if os.getenv('RAILWAY_ENVIRONMENT'):
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://{os.getenv('RAILWAY_STATIC_URL')}/{TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == '__main__':
    main()
