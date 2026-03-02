# Di bagian akhir file main.py Anda, pastikan ada:
def main():
    """Main function to run the bot"""
    try:
        bot = ProductionDuplicateBot()
        
        # Pilih mode berdasarkan environment
        use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
        
        if use_webhook:
            bot.run_webhook()
        else:
            bot.run_polling()
            
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
