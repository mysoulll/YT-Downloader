import os
import re
import logging
import asyncio
from typing import Dict
from pytube import YouTube
from pytube.exceptions import VideoUnavailable, RegexMatchError, PytubeError
from moviepy.editor import VideoFileClip
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.constants import ChatAction, ParseMode
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
TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN')  # Gunakan environment variable atau token langsung
TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# State conversation
MENU, PROCESSING_LINK, CHOOSING_FORMAT = range(3)

class YouTubeDownloader:
    @staticmethod
    async def validate_url(url: str) -> bool:
        """Validasi URL YouTube dengan regex yang lebih komprehensif"""
        patterns = [
            r'(https?://)?(www\.)?youtube\.com/watch\?v=([^&]+)',
            r'(https?://)?(www\.)?youtu\.be/([^?]+)',
            r'(https?://)?(www\.)?youtube\.com/shorts/([^?]+)',
            r'(https?://)?(www\.)?youtube\.com/embed/([^?]+)'
        ]
        return any(re.match(pattern, url) for pattern in patterns)

    @staticmethod
    async def get_video_info(url: str):
        """Dapatkan info video dengan error handling"""
        try:
            yt = YouTube(url)
            # Test akses ke properti dasar
            if not all([yt.title, yt.author, yt.length]):
                raise VideoUnavailable("Video info tidak lengkap")
            return yt
        except VideoUnavailable as e:
            raise ValueError(f"Video tidak tersedia: {str(e)}")
        except RegexMatchError:
            raise ValueError("URL YouTube tidak valid")
        except PytubeError as e:
            raise ValueError(f"Error pytube: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error tak terduga: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /start"""
    try:
        welcome_msg = """
🌟 <b>YouTube Downloader Premium</b> 🌟

🎬 Download video/audio dari YouTube
🎧 Konversi ke MP3 berkualitas tinggi
🎥 Dapatkan video dalam resolusi HD

Pilih opsi:"""
        
        buttons = [
            [InlineKeyboardButton("📥 Download Konten", callback_data='download')],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data='help')]
        ]
        
        await update.message.reply_text(
            text=welcome_msg,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
        return MENU
    except Exception as e:
        logger.error(f"Error di start: {e}")
        await update.message.reply_text(
            "❌ Terjadi error saat memulai bot. Silakan coba lagi.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle permintaan download"""
    try:
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            text="📩 <b>Silakan kirim link YouTube:</b>\n\n"
                 "Contoh: https://youtu.be/contoh\n"
                 "atau https://www.youtube.com/watch?v=contoh",
            parse_mode=ParseMode.HTML
        )
        return PROCESSING_LINK
    except Exception as e:
        logger.error(f"Error di handle_download: {e}")
        await update.callback_query.message.reply_text(
            "❌ Gagal memproses permintaan. Silakan coba lagi.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses link YouTube"""
    try:
        url = update.message.text.strip()
        
        # Validasi URL
        if not await YouTubeDownloader.validate_url(url):
            await update.message.reply_text(
                "❌ <b>Format URL tidak valid!</b>\n"
                "Pastikan link berasal dari YouTube.\n"
                "Contoh yang valid:\n"
                "• https://youtu.be/abc123\n"
                "• https://www.youtube.com/watch?v=abc123",
                parse_mode=ParseMode.HTML
            )
            return PROCESSING_LINK
        
        await update.message.reply_chat_action(ChatAction.TYPING)
        
        # Dapatkan info video
        try:
            yt = await YouTubeDownloader.get_video_info(url)
        except ValueError as e:
            await update.message.reply_text(
                f"❌ <b>{str(e)}</b>\n"
                "Silakan coba dengan link yang berbeda.",
                parse_mode=ParseMode.HTML
            )
            return PROCESSING_LINK
        
        # Simpan info video
        context.user_data['video_info'] = {
            'url': url,
            'title': yt.title[:100],  # Batasi panjang judul
            'author': yt.author,
            'length': yt.length,
            'yt_object': yt  # Simpan objek YouTube untuk digunakan nanti
        }
        
        # Tampilkan info video
        duration = f"{yt.length // 60}:{yt.length % 60:02d}"
        caption = f"""
🎬 <b>{yt.title}</b>

👤 <i>Channel:</i> {yt.author}
⏱ <i>Durasi:</i> {duration}

Pilih format download:"""
        
        buttons = [
            [InlineKeyboardButton("🎧 MP3 (Audio)", callback_data='mp3'),
             InlineKeyboardButton("🎥 MP4 (Video)", callback_data='mp4')],
            [InlineKeyboardButton("⬅️ Kembali", callback_data='back')]
        ]
        
        try:
            # Coba kirim dengan thumbnail
            thumb_url = yt.thumbnail_url.replace('default.jpg', 'hqdefault.jpg')
            await update.message.reply_photo(
                photo=thumb_url,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            # Fallback ke text jika thumbnail gagal
            await update.message.reply_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )
        
        return CHOOSING_FORMAT
        
    except Exception as e:
        logger.error(f"Error di process_link: {e}")
        await update.message.reply_text(
            "❌ <b>Terjadi error saat memproses link!</b>\n"
            "Silakan coba lagi atau gunakan link yang berbeda.",
            parse_mode=ParseMode.HTML
        )
        return PROCESSING_LINK

async def download_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download dan konversi ke MP3"""
    query = update.callback_query
    await query.answer()
    
    try:
        video_info = context.user_data.get('video_info')
        if not video_info:
            raise ValueError("Sesi telah berakhir")
        
        yt = video_info['yt_object']
        chat_id = update.effective_chat.id
        
        # Step 1: Persiapkan download
        await query.edit_message_text(
            text="⏳ <b>Mempersiapkan download audio...</b>",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_AUDIO)
        
        # Step 2: Download video
        try:
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution').desc().first()
            
            if not stream:
                raise ValueError("Tidak bisa menemukan stream yang sesuai")
            
            video_path = stream.download(
                output_path=TEMP_DIR,
                filename_prefix="temp_"
            )
        except Exception as e:
            raise ValueError(f"Gagal mendownload video: {str(e)}")
        
        # Step 3: Konversi ke MP3
        await query.edit_message_text(
            text="🔧 <b>Mengkonversi ke MP3...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            mp3_path = os.path.join(TEMP_DIR, f"{video_info['title'][:50]}.mp3")
            video_clip = VideoFileClip(video_path)
            audio_clip = video_clip.audio
            audio_clip.write_audiofile(mp3_path)
            audio_clip.close()
            video_clip.close()
        except Exception as e:
            raise ValueError(f"Konversi gagal: {str(e)}")
        
        # Step 4: Kirim audio
        await query.edit_message_text(
            text="📤 <b>Mengunggah audio...</b>",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)
        
        try:
            with open(mp3_path, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=video_info['title'][:30],
                    performer=video_info['author'],
                    duration=video_info['length'],
                    read_timeout=60,
                    write_timeout=60
                )
        except Exception as e:
            raise ValueError(f"Upload gagal: {str(e)}")
        
        # Bersihkan file
        for file_path in [video_path, mp3_path]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Error membersihkan file: {str(e)}")
        
        # Pesan sukses
        await query.edit_message_text(
            text="✅ <b>Audio berhasil diunduh!</b>\n"
                 "Selamat menikmati musiknya! 🎧",
            parse_mode=ParseMode.HTML
        )
        
        return MENU
        
    except ValueError as e:
        await query.edit_message_text(
            text=f"❌ <b>Error:</b> {str(e)}\n\n"
                 "Silakan coba lagi atau mulai sesi baru dengan /start",
            parse_mode=ParseMode.HTML
        )
        return MENU
        
    except Exception as e:
        logger.error(f"Error tak terduga di download_mp3: {str(e)}")
        await query.edit_message_text(
            text="❌ <b>Terjadi error tak terduga!</b>\n"
                 "Silakan coba lagi nanti.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def download_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download sebagai MP4"""
    query = update.callback_query
    await query.answer()
    
    try:
        video_info = context.user_data.get('video_info')
        if not video_info:
            raise ValueError("Sesi telah berakhir")
        
        yt = video_info['yt_object']
        chat_id = update.effective_chat.id
        
        # Step 1: Persiapkan download
        await query.edit_message_text(
            text="⏳ <b>Mempersiapkan download video...</b>",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VIDEO)
        
        # Step 2: Download video
        try:
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution').desc().first()
            
            if not stream:
                raise ValueError("Tidak bisa menemukan stream yang sesuai")
            
            video_path = stream.download(
                output_path=TEMP_DIR,
                filename_prefix="video_"
            )
        except Exception as e:
            raise ValueError(f"Gagal mendownload video: {str(e)}")
        
        # Step 3: Kirim video
        await query.edit_message_text(
            text="📤 <b>Mengunggah video...</b>",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        
        try:
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption=video_info['title'][:60],
                    supports_streaming=True,
                    width=1280,
                    height=720,
                    read_timeout=60,
                    write_timeout=60
                )
        except Exception as e:
            raise ValueError(f"Upload gagal: {str(e)}")
        
        # Bersihkan file
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logger.error(f"Error membersihkan file: {str(e)}")
        
        # Pesan sukses
        await query.edit_message_text(
            text="✅ <b>Video berhasil diunduh!</b>\n"
                 "Selamat menonton! 🎬",
            parse_mode=ParseMode.HTML
        )
        
        return MENU
        
    except ValueError as e:
        await query.edit_message_text(
            text=f"❌ <b>Error:</b> {str(e)}\n\n"
                 "Silakan coba lagi atau mulai sesi baru dengan /start",
            parse_mode=ParseMode.HTML
        )
        return MENU
        
    except Exception as e:
        logger.error(f"Error tak terduga di download_mp4: {str(e)}")
        await query.edit_message_text(
            text="❌ <b>Terjadi error tak terduga!</b>\n"
                 "Silakan coba lagi nanti.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pesan bantuan"""
    try:
        help_text = """
ℹ️ <b>Bantuan YouTube Downloader</b>

🔹 <u>Cara menggunakan:</u>
1. Pilih menu Download
2. Kirim link video YouTube
3. Pilih format (MP3/MP4)
4. Tunggu proses selesai

⚠️ <u>Catatan:</u>
- Maksimal ukuran video 50MB
- Hasil download bersifat sementara
- Untuk video panjang, proses mungkin memakan waktu

🔗 <u>Contoh link yang valid:</u>
- https://youtu.be/contoh
- https://www.youtube.com/watch?v=contoh
- https://youtube.com/shorts/contoh"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data='back')]
        ]
        
        await update.message.reply_text(
            text=help_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
        return MENU
    except Exception as e:
        logger.error(f"Error di help_command: {e}")
        await update.message.reply_text(
            "❌ Gagal menampilkan bantuan. Silakan coba lagi.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kembali ke menu utama"""
    try:
        query = update.callback_query
        await query.answer()
        
        await start(update, context)
        return MENU
    except Exception as e:
        logger.error(f"Error di cancel: {e}")
        return MENU

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Menangani semua error yang tidak tertangani"""
    logger.error("Exception:", exc_info=context.error)
    
    error_text = """
❌ <b>Terjadi Kesalahan!</b>

Maaf, terjadi masalah saat memproses permintaan Anda.
Silakan coba lagi atau mulai sesi baru dengan /start"""
    
    try:
        if isinstance(update, Update):
            if update.message:
                await update.message.reply_text(
                    text=error_text,
                    parse_mode=ParseMode.HTML
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    text=error_text,
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error di error_handler: {e}")
    
    return MENU

def main():
    """Jalankan bot"""
    try:
        # Buat aplikasi dengan timeout yang lebih panjang
        application = Application.builder() \
            .token(TOKEN) \
            .read_timeout(60) \
            .write_timeout(60) \
            .connect_timeout(30) \
            .pool_timeout(60) \
            .build()
        
        # Setup ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                MENU: [
                    CallbackQueryHandler(handle_download, pattern='^download$'),
                    CallbackQueryHandler(help_command, pattern='^help$'),
                    CallbackQueryHandler(cancel, pattern='^back$')
                ],
                PROCESSING_LINK: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_link),
                    CallbackQueryHandler(cancel, pattern='^back$')
                ],
                CHOOSING_FORMAT: [
                    CallbackQueryHandler(download_mp3, pattern='^mp3$'),
                    CallbackQueryHandler(download_mp4, pattern='^mp4$'),
                    CallbackQueryHandler(cancel, pattern='^back$')
                ]
            },
            fallbacks=[CommandHandler('start', start)],
            conversation_timeout=300  # 5 menit timeout untuk conversation
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        
        # Jalankan bot
        logger.info("Bot sedang berjalan...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Error di main: {e}")
        raise

if __name__ == '__main__':
    main()
