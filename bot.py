#!/usr/bin/env python3
"""
ChefLink Telegram Bot
Run this script to start the Telegram bot.
"""
import asyncio
import logging
import sys

from app.services.telegram.bot import ChefLinkBot

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Main function to run the bot."""
    try:
        bot = ChefLinkBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()