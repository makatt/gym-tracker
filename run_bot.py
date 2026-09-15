"""Точка входа бота: python run_bot.py"""

import asyncio

from app.bot import main

if __name__ == "__main__":
    asyncio.run(main())
