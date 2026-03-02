def main():
    """Main function to run the bot"""
    bot = None  # Inisialisasi bot sebagai None
    try:
        bot = ProductionDuplicateBot()
        
        # Pilih mode berdasarkan environment
        use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
        
        if use_webhook:
            bot.run_webhook()
        else:
            bot.run_polling()
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        if bot and hasattr(bot, 'conn') and bot.conn:
            bot.conn.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        # Jangan akses bot.conn di sini karena mungkin bot tidak terinisialisasi
        sys.exit(1)

if __name__ == "__main__":
    main()
