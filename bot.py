import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters, CommandHandler
from telegram import Update
import sqlite3
import hashlib
from datetime import datetime
import signal
import sys
import pytz
import traceback

# Setup logging dengan encoding UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Set timezone untuk logging ke Jakarta
logging.Formatter.converter = lambda *args: datetime.now(pytz.timezone('Asia/Jakarta')).timetuple()

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class ProductionDuplicateBot:
    def __init__(self):
        self.conn = None
        self.app = None
        self.timezone = pytz.timezone('Asia/Jakarta')
        
        try:
            # Load environment variables
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
            if os.path.exists(env_path):
                load_dotenv(env_path)
                logger.info("✅ Environment variables loaded from .env file")
            else:
                logger.info("📝 Using environment variables from system")
            
            # Get bot token
            self.token = os.getenv('BOT_TOKEN')
            if not self.token:
                raise ValueError("❌ BOT_TOKEN tidak ditemukan! Set BOT_TOKEN di environment variables")
            
            # Inisialisasi aplikasi Telegram
            self.app = Application.builder().token(self.token).build()
            
            # Setup komponen bot
            self.setup_database()
            self.setup_handlers()
            self.setup_error_handler()
            self.setup_signal_handlers()
            
            logger.info("🤖 Bot berhasil diinisialisasi dengan zona waktu Jakarta")
            logger.info(f"📊 Mode: {'Webhook' if os.getenv('USE_WEBHOOK', 'false').lower() == 'true' else 'Polling'}")
            
        except Exception as e:
            logger.error(f"❌ Gagal menginisialisasi bot: {e}")
            logger.error(traceback.format_exc())
            if self.conn:
                self.conn.close()
            raise
    
    def setup_database(self):
        """Setup database dengan path yang lebih baik"""
        try:
            db_path = os.getenv('DB_PATH', 'messages.db')
            
            # Pastikan direktori untuk database ada
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"📁 Membuat direktori database: {db_dir}")
            
            # Koneksi ke database
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            cursor = self.conn.cursor()
            
            # Buat tabel jika belum ada
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    message_hash TEXT,
                    message_text TEXT,
                    user_id INTEGER,
                    timestamp DATETIME,
                    user_name TEXT DEFAULT "Unknown",
                    UNIQUE(chat_id, message_hash)
                )
            ''')
            
            # Buat index untuk optimasi query
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_hash ON messages(chat_id, message_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)')
            
            self.conn.commit()
            logger.info(f"📊 Database terinisialisasi di: {db_path}")
            
            # Test koneksi
            cursor.execute("SELECT COUNT(*) FROM messages")
            count = cursor.fetchone()[0]
            logger.info(f"📈 Total pesan tersimpan: {count}")
            
        except sqlite3.Error as e:
            logger.error(f"❌ Error database: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error tidak terduga saat setup database: {e}")
            raise
    
    def setup_handlers(self):
        """Setup handler untuk pesan dan commands"""
        try:
            # Handler untuk command /health
            self.app.add_handler(CommandHandler("health", self.health_check))
            self.app.add_handler(CommandHandler("status", self.health_check))
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            
            # Handler untuk pesan teks
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            logger.info("✅ Message handlers registered")
        except Exception as e:
            logger.error(f"❌ Error setup handlers: {e}")
            raise
    
    def setup_error_handler(self):
        """Handle errors untuk production"""
        async def error_handler(update: Update, context):
            try:
                logger.error(f"❌ Error occurred: {context.error}")
                logger.error(traceback.format_exc())
                
                # Kirim pesan error ke admin jika ada
                admin_id = os.getenv('ADMIN_ID')
                if admin_id and update and update.effective_chat:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"⚠️ Error di bot:\n{str(context.error)[:200]}"
                        )
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error in error handler: {e}")
            
        self.app.add_error_handler(error_handler)
        logger.info("✅ Error handler registered")
    
    def setup_signal_handlers(self):
        """Handle shutdown signals"""
        def signal_handler(signum, frame):
            logger.info(f"🛑 Menerima signal shutdown: {signum}")
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.graceful_shutdown())
            except RuntimeError:
                # Jika tidak ada event loop, buat yang baru
                asyncio.run(self.graceful_shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("✅ Signal handlers registered")
    
    async def graceful_shutdown(self):
        """Shutdown yang graceful"""
        try:
            logger.info("🔚 Memulai shutdown graceful...")
            
            # Tutup koneksi database
            if hasattr(self, 'conn') and self.conn:
                self.conn.close()
                logger.info("✅ Database connection closed")
            
            # Shutdown aplikasi
            if hasattr(self, 'app') and self.app:
                await self.app.shutdown()
                logger.info("✅ Application shutdown complete")
            
            logger.info("👋 Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
            logger.error(traceback.format_exc())
        finally:
            sys.exit(0)
    
    def generate_message_hash(self, text):
        """Generate hash untuk pesan untuk deteksi duplikat"""
        try:
            normalized_text = ' '.join(text.lower().split())
            return hashlib.md5(normalized_text.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error generating hash: {e}")
            return hashlib.md5(str(datetime.now()).encode()).hexdigest()
    
    def get_current_time(self):
        """Mendapatkan waktu saat ini dalam zona waktu Jakarta"""
        return datetime.now(self.timezone)
    
    def format_time_for_db(self, dt=None):
        """Format waktu untuk penyimpanan di database"""
        if dt is None:
            dt = self.get_current_time()
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    def format_time_display(self, dt_str):
        """Format waktu untuk ditampilkan ke user"""
        try:
            # Parse waktu dari database
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            # Pastikan waktu memiliki timezone Jakarta
            if dt.tzinfo is None:
                dt = self.timezone.localize(dt)
            return dt.strftime('%Y/%m/%d %H:%M:%S')
        except Exception as e:
            logger.error(f"Error formatting time: {e}")
            return dt_str
    
    async def health_check(self, update: Update, context):
        """Health check endpoint untuk monitoring"""
        try:
            current_time = self.format_time_display(self.format_time_for_db())
            
            # Cek koneksi database
            db_status = "✅ Active"
            if self.conn:
                try:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM messages")
                    count = cursor.fetchone()[0]
                    db_status = f"✅ Active ({count} messages)"
                except:
                    db_status = "❌ Error"
            
            status_message = (
                f"🤖 **BOT STATUS**\n"
                f"Waktu: {current_time} WIB\n"
                f"Database: {db_status}\n"
                f"Mode: {os.getenv('USE_WEBHOOK', 'Polling')}\n"
                f"Status: 🟢 ONLINE"
            )
            
            await update.message.reply_text(status_message, parse_mode='Markdown')
            logger.info(f"✅ Health check from user {update.effective_user.id}")
            
        except Exception as e:
            logger.error(f"Error in health_check: {e}")
            await update.message.reply_text("❌ Error checking status")
    
    async def start_command(self, update: Update, context):
        """Handler untuk command /start"""
        welcome_message = (
            "👋 **Selamat datang di Duplicate Detection Bot!**\n\n"
            "Bot ini akan mendeteksi pesan duplikat dalam 24 jam terakhir.\n\n"
            "**Commands:**\n"
            "/start - Menampilkan pesan ini\n"
            "/help - Bantuan penggunaan\n"
            "/health - Status bot\n\n"
            "**Cara kerja:**\n"
            "Jika ada pesan yang sama dikirim dalam 24 jam, bot akan memberi notifikasi."
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context):
        """Handler untuk command /help"""
        help_message = (
            "📚 **Bantuan Penggunaan**\n\n"
            "Bot ini otomatis mendeteksi pesan duplikat.\n\n"
            "**Fitur:**\n"
            "• Deteksi pesan teks duplikat dalam 24 jam\n"
            "• Menampilkan siapa yang pertama kali mengirim\n"
            "• Waktu dalam zona WIB (Jakarta)\n"
            "• Penyimpanan pesan 7 hari\n\n"
            "**Catatan:**\n"
            "• Minimal 5 karakter untuk deteksi\n"
            "• Spasi berlebih akan dinormalisasi\n"
            "• Case insensitive (huruf besar/kecil diabaikan)"
        )
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context):
        """Handle incoming messages"""
        try:
            message = update.message
            if not message or not message.text:
                return
            
            chat_id = message.chat_id
            user_id = message.from_user.id
            user_name = message.from_user.first_name or message.from_user.username or str(user_id)
            message_text = message.text
            
            # Skip jika pesan terlalu pendek
            if len(message_text.strip()) < 5:
                return
            
            message_hash = self.generate_message_hash(message_text)
            
            # Pastikan koneksi database masih terbuka
            if not self.conn:
                logger.error("❌ Database connection is closed")
                try:
                    self.setup_database()
                except:
                    return
            
            cursor = self.conn.cursor()
            
            # Cek apakah pesan sudah pernah dikirim dalam 24 jam terakhir
            cursor.execute('''
                SELECT user_id, message_text, timestamp, user_name 
                FROM messages 
                WHERE chat_id = ? AND message_hash = ? 
                AND timestamp > datetime('now', '-1 day')
                ORDER BY timestamp ASC
                LIMIT 1
            ''', (chat_id, message_hash))
            
            existing_message = cursor.fetchone()
            
            if existing_message:
                original_user_id, original_text, original_time, original_user_name = existing_message
                
                # Format waktu untuk ditampilkan
                original_time_str = self.format_time_display(original_time)
                current_time_str = self.format_time_display(self.format_time_for_db())
                
                response_message = (
                    f"❌ **DETEKSI SISTEM** ❌\n"
                    f"**TEXT:** {original_text}\n"
                    f"**Pertama:** {original_user_name} : {original_time_str} WIB\n"
                    f"**Duplikat:** {user_name} : {current_time_str} WIB"
                )
                
                await message.reply_text(response_message, parse_mode='Markdown')
                logger.info(f"🚫 Duplicate detected - Chat: {chat_id}, User: {user_name}")
            else:
                # Simpan pesan baru ke database dengan waktu Jakarta
                current_time = self.format_time_for_db()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO messages 
                    (chat_id, message_hash, message_text, user_id, timestamp, user_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (chat_id, message_hash, message_text, user_id, current_time, user_name))
                self.conn.commit()
                
                logger.info(f"✅ New message saved - Chat: {chat_id}, User: {user_name}")
            # Coba reconnect database
            try:
                self.setup_database()
            except:
                pass
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
            logger.error(traceback.format_exc())
    
    def run_polling(self):
        """Jalankan dengan polling (untuk development)"""
        try:
            current_time = self.format_time_display(self.format_time_for_db())
            logger.info(f"🔄 Starting bot with polling at {current_time} WIB...")
            logger.info("📱 Bot is running. Press Ctrl+C to stop.")
            
            self.app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                timeout=30
            )
        except Exception as e:
            logger.error(f"❌ Error in polling: {e}")
            raise
    
    def run_webhook(self):
        """Jalankan dengan webhook (untuk production di Railway)"""
        try:
            webhook_url = os.getenv('WEBHOOK_URL')
            port = int(os.getenv('PORT', 8080))
            
            if not webhook_url:
                logger.warning("⚠️ WEBHOOK_URL not set, falling back to polling")
                return self.run_polling()
            
            current_time = self.format_time_display(self.format_time_for_db())
            logger.info(f"🌐 Starting bot with webhook at {current_time} WIB")
            logger.info(f"🌐 Webhook URL: {webhook_url}")
            logger.info(f"🌐 Port: {port}")
            
            self.app.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=self.token,
                webhook_url=f"{webhook_url}/{self.token}",
                drop_pending_updates=True,
                secret_token=os.getenv('WEBHOOK_SECRET', ''),
                max_connections=40
            )
        except Exception as e:
            logger.error(f"❌ Error in webhook: {e}")
            raise

def main():
    """Main function to run the bot"""
    bot = None
    try:
        # Log environment info
        logger.info("=" * 50)
        logger.info("🚀 STARTING BOT")
        logger.info("=" * 50)
        
        # Inisialisasi bot
        bot = ProductionDuplicateBot()
        
        # Pilih mode berdasarkan environment
        use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
        
        if use_webhook:
            bot.run_webhook()
        else:
            bot.run_polling()
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user (Ctrl+C)")
        if bot and hasattr(bot, 'conn') and bot.conn:
            bot.conn.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        if bot and hasattr(bot, 'conn') and bot.conn:
            bot.conn.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
