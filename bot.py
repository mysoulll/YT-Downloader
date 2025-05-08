import os
import re
import logging
import asyncio
from typing import Dict
from pytube import YouTube
from moviepy.editor import VideoFileClip
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
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

# Configuration
TOKEN = os.getenv('TELEGRAM_TOKEN') or "YOUR_BOT_TOKEN"  # Fallback for local testing
TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
MENU, PROCESSING_LINK, CHOOSING_FORMAT = range(3)

class BotUI:
    """Class for rich interactive UI elements"""
    @staticmethod
    async def show_main_menu(update: Update):
        """Show beautiful main menu with interactive buttons"""
        menu_text = """
🌟 <b>YouTube Downloader Premium</b> 🌟

🎬 Download video/audio from YouTube
🎧 Convert to MP3 with high quality
🎥 Get videos in HD resolution

Choose an option:"""
        
        buttons = [
            [InlineKeyboardButton("📥 Download Content", callback_data='download')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
             InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]
        
        await update.message.reply_text(
            text=menu_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )

    @staticmethod
    async def show_video_info(update: Update, yt: YouTube):
        """Show beautiful video info card"""
        duration = f"{yt.length // 60}:{yt.length % 60:02d}"
        views = f"{yt.views:,}".replace(",", ".")
        
        caption = f"""
🎬 <b>{yt.title}</b>

👤 <i>Channel:</i> {yt.author}
⏱ <i>Duration:</i> {duration}
👀 <i>Views:</i> {views}

Choose download format:"""
        
        buttons = [
            [InlineKeyboardButton("🎧 MP3 (Audio)", callback_data='mp3'),
             InlineKeyboardButton("🎥 MP4 (Video)", callback_data='mp4')],
            [InlineKeyboardButton("📺 Preview", callback_data='preview'),
             InlineKeyboardButton("⬅️ Back", callback_data='back')]
        ]
        
        try:
            # Try to send with thumbnail
            thumb_url = yt.thumbnail_url.replace('default.jpg', 'hqdefault.jpg')
            await update.message.reply_photo(
                photo=thumb_url,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending thumbnail: {e}")
            await update.message.reply_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )

    @staticmethod
    async def show_progress(update: Update, current: int, total: int, file_type: str):
        """Show beautiful progress bar"""
        percent = current / total
        progress_bar = "🟩" * int(percent * 10) + "⬜️" * (10 - int(percent * 10))
        
        text = f"""
⏳ <b>Downloading {file_type.upper()}...</b>

{progress_bar} {percent:.1%}

📦 {current/(1024*1024):.1f}MB / {total/(1024*1024):.1f}MB"""
        
        try:
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode=ParseMode.HTML
            )
        except:
            pass

class YouTubeDownloader:
    """Core downloader functionality"""
    @staticmethod
    async def download_video(yt: YouTube, quality: str = "highest"):
        """Download YouTube video"""
        if quality == "highest":
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution').desc().first()
        else:
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4',
                resolution=quality
            ).first()
        
        return stream.download(output_path=TEMP_DIR)

    @staticmethod
    async def convert_to_mp3(video_path: str):
        """Convert video to MP3"""
        mp3_path = os.path.join(TEMP_DIR, "audio.mp3")
        video_clip = VideoFileClip(video_path)
        audio_clip = video_clip.audio
        audio_clip.write_audiofile(mp3_path)
        audio_clip.close()
        video_clip.close()
        return mp3_path

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await BotUI.show_main_menu(update)
    return MENU

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download request"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        text="📩 <b>Please send me the YouTube link:</b>\n\n"
             "Example: https://youtu.be/example",
        parse_mode=ParseMode.HTML
    )
    return PROCESSING_LINK

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process YouTube link"""
    url = update.message.text
    
    # Validate URL
    if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/', url):
        await update.message.reply_text(
            "❌ <b>Invalid YouTube URL!</b>\n"
            "Please send a valid YouTube link.",
            parse_mode=ParseMode.HTML
        )
        return PROCESSING_LINK
    
    try:
        await update.message.reply_chat_action(ChatAction.TYPING)
        yt = YouTube(url)
        
        # Save video info for later use
        context.user_data['video_info'] = {
            'url': url,
            'title': yt.title,
            'author': yt.author,
            'length': yt.length
        }
        
        await BotUI.show_video_info(update, yt)
        return CHOOSING_FORMAT
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await update.message.reply_text(
            "❌ <b>Error processing video!</b>\n"
            "Please try another link.",
            parse_mode=ParseMode.HTML
        )
        return PROCESSING_LINK

async def download_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle MP3 download request"""
    query = update.callback_query
    await query.answer()
    
    video_info = context.user_data.get('video_info')
    if not video_info:
        await query.edit_message_text("❌ Session expired! Please start again.")
        return MENU
    
    try:
        await query.edit_message_text("⏳ <b>Preparing audio download...</b>", parse_mode=ParseMode.HTML)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_AUDIO)
        
        yt = YouTube(video_info['url'])
        
        # Download with progress
        video_path = await YouTubeDownloader.download_video(yt)
        await BotUI.show_progress(update, 50, 100, "MP3")
        
        # Convert to MP3
        await query.edit_message_text("🔄 <b>Converting to MP3...</b>", parse_mode=ParseMode.HTML)
        mp3_path = await YouTubeDownloader.convert_to_mp3(video_path)
        await BotUI.show_progress(update, 80, 100, "MP3")
        
        # Send audio file
        await query.edit_message_text("📤 <b>Uploading audio...</b>", parse_mode=ParseMode.HTML)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_AUDIO)
        
        with open(mp3_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=audio_file,
                title=video_info['title'][:30],
                performer=video_info['author'],
                duration=video_info['length']
            )
        
        # Cleanup
        os.remove(video_path)
        os.remove(mp3_path)
        
        await query.edit_message_text(
            "✅ <b>Audio download complete!</b>\n"
            "Enjoy your music! 🎧",
            parse_mode=ParseMode.HTML
        )
        
        await BotUI.show_main_menu(update)
        return MENU
        
    except Exception as e:
        logger.error(f"MP3 download error: {e}")
        await query.edit_message_text(
            "❌ <b>Failed to download audio!</b>\n"
            "Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def download_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle MP4 download request"""
    query = update.callback_query
    await query.answer()
    
    video_info = context.user_data.get('video_info')
    if not video_info:
        await query.edit_message_text("❌ Session expired! Please start again.")
        return MENU
    
    try:
        await query.edit_message_text("⏳ <b>Preparing video download...</b>", parse_mode=ParseMode.HTML)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VIDEO)
        
        yt = YouTube(video_info['url'])
        
        # Download with progress
        video_path = await YouTubeDownloader.download_video(yt)
        await BotUI.show_progress(update, 50, 100, "MP4")
        
        # Send video file
        await query.edit_message_text("📤 <b>Uploading video...</b>", parse_mode=ParseMode.HTML)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VIDEO)
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=video_info['title'][:60],
                supports_streaming=True,
                width=1280,
                height=720
            )
        
        # Cleanup
        os.remove(video_path)
        
        await query.edit_message_text(
            "✅ <b>Video download complete!</b>\n"
            "Enjoy your video! 🎬",
            parse_mode=ParseMode.HTML
        )
        
        await BotUI.show_main_menu(update)
        return MENU
        
    except Exception as e:
        logger.error(f"MP4 download error: {e}")
        await query.edit_message_text(
            "❌ <b>Failed to download video!</b>\n"
            "Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    await BotUI.show_main_menu(update)
    return MENU

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logger.error("Exception:", exc_info=context.error)
    
    error_text = """
❌ <b>Something went wrong!</b>

We encountered an unexpected error. 
Please try again or /start a new session."""
    
    if isinstance(update, Update):
        if update.message:
            await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)
        elif update.callback_query:
            await update.callback_query.message.reply_text(error_text, parse_mode=ParseMode.HTML)
    
    return MENU

def main():
    """Start the bot"""
    # Create application with timeout settings
    application = Application.builder() \
        .token(TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .connect_timeout(30) \
        .build()
    
    # Setup conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MENU: [
                CallbackQueryHandler(handle_download, pattern='^download$'),
                CallbackQueryHandler(cancel, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^settings$'),
                CallbackQueryHandler(cancel, pattern='^help$')
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
        conversation_timeout=300  # 5 minutes timeout
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Run bot
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
