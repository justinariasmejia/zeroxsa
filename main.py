import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from utils_db import init_db, load_server_config
from cogs.letters import MailboxView
from cogs.tickets import TicketView, TicketControlView
from cogs.birthdays import BirthdayView

load_dotenv()

# We need a custom bot class that knows its target ID to sync commands ONLY there
class ValentineBot(commands.Bot):
    def __init__(self, target_guild_id: int, bot_name: str, config: dict):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.target_guild_id = target_guild_id
        self.bot_name = bot_name
        self.config = config

    async def setup_hook(self):
        # Initialize DBs (Safe to call multiple times as it checks if exists)
        await init_db([self.target_guild_id])
        
        # Load extensions based on CONFIG
        if self.config.get('enable_letters', True):
            await self.load_extension("cogs.letters")
            self.add_view(MailboxView())
            print(f"   [Feature] 💌 Cartas ACTIVADO")

        if self.config.get('enable_tickets', True):
            await self.load_extension("cogs.tickets")
            self.add_view(TicketView())
            self.add_view(TicketControlView())
            print(f"   [Feature] 🎫 Tickets ACTIVADO")

        if self.config.get('enable_birthdays', True):
            await self.load_extension("cogs.birthdays")
            self.add_view(BirthdayView())
            print(f"   [Feature] 🎂 Cumpleaños ACTIVADO")

        # Sync ONLY to the specific guild
        if self.target_guild_id:
            guild = discord.Object(id=self.target_guild_id)
            self.tree.copy_global_to(guild=guild)
            try:
                await self.tree.sync(guild=guild)
                print(f"✅ [{self.bot_name}] Comandos sincronizados en servidor {self.target_guild_id}")
            except Exception as e:
                print(f"❌ [{self.bot_name}] Error sincronizando en {self.target_guild_id}: {e}")
        
    async def on_ready(self):
         print(f"🟢 [{self.bot_name}] Conectado correctamente como {self.user} (ID: {self.user.id})")

# Simple Log Bot Class
class LogBot(commands.Bot):
    def __init__(self, bot_name: str):
        super().__init__(command_prefix="?", intents=discord.Intents.default())
        self.bot_name = bot_name

    async def on_ready(self):
        print(f"🟣 [{self.bot_name}] Log Bot conectado como {self.user}")

async def safe_start(bot, token):
    try:
        await bot.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        print(f"\n🛑 CRÍTICO: El bot [{getattr(bot, 'bot_name', 'Unknown')}] falló al iniciar.")
        print(f"   ↳ CAUSA: Faltan 'Privileged Intents' (Intents Privilegiados).")
        print(f"   ↳ SOLUCIÓN: Ve al Discord Developer Portal -> Bot -> Privileged Gateway Intents")
        print(f"   ↳ ACTIVA: 'Server Members Intent' (y 'Message Content Intent' si es necesario).\n")
    except discord.errors.LoginFailure:
        print(f"\n🛑 ERROR DE LOGIN: El token del bot [{getattr(bot, 'bot_name', 'Unknown')}] es inválido.\n")
    except Exception as e:
        print(f"\n❌ Error desconocido en [{getattr(bot, 'bot_name', 'Unknown')}]: {e}\n")

async def main_runner():
    server_config = load_server_config()
    
    tasks = []
    
    print("🚀 Inicializando sistema Multi-Bot...")

    # Iterate over configs
    for guild_id, conf in server_config.items():
        # Determine Name and Emoji
        if guild_id == 1237573087013109811:
            name = "Comunidad Zero"
            emoji = "🟢"
        elif guild_id == 1091109766237007992:
            name = "Comunidad SA Iglesia"
            emoji = "🟣"
        else:
            name = f"Guild {guild_id}"
            emoji = "⚪"

        print(f"🔹 Preparando bots para: {name} {emoji}")

        # 1. Main Bot
        token = conf.get('token')
        if token:
            bot = ValentineBot(target_guild_id=guild_id, bot_name=f"{emoji} [{name} - Main]", config=conf)
            tasks.append(safe_start(bot, token))
        else:
            print(f"⚠️ Falta TOKEN principal para {name}")

        # 2. Log Bot
        log_token = conf.get('log_token')
        if log_token:
            # Check if it's the same as main token to avoid conflict (user might re-use)
            if log_token == token:
                print(f"⚠️ LOG_TOKEN es igual al TOKEN principal en {name}. Saltando Log Bot secundario.")
            else:
                lbot = LogBot(bot_name=f"{emoji} [{name} - Logs]")
                tasks.append(safe_start(lbot, log_token))
        else:
            print(f"ℹ️ No hay LOG_TOKEN para {name}. Se omitirá el bot de logs.")

    if not tasks:
        print("❌ No hay bots para iniciar. Revisa el .env")
        return

    print(f"⚡ Iniciando {len(tasks)} procesos de bot...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main_runner())
    except KeyboardInterrupt:
        pass
