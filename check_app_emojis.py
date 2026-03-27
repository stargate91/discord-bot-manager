import discord
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class TestBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        print("-" * 20)
        
        # Check Application Emojis
        try:
            app = await self.application_info()
            print(f"Application: {app.name}")
            
            # Fetch application emojis (new in latest d.py)
            emojis = await self.fetch_application_emojis()
            print(f"Found {len(emojis)} Application Emojis:")
            for e in emojis:
                print(f"• {e.name} | ID: {e.id} | animated: {e.animated}")
                print(f"  Str: '{str(e)}' | Repr: {repr(e)}")
            
        except Exception as e:
            print(f"Error fetching app emojis: {e}")
            
        await self.close()

if __name__ == "__main__":
    if TOKEN:
        bot = TestBot()
        asyncio.run(bot.start(TOKEN))
    else:
        print("TOKEN NOT FOUND")
