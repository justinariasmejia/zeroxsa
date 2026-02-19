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
        intents.message_content = True
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

        # Load Admin Config always
        await self.load_extension("cogs.admin")
        print(f"   [Feature] 🛡️ Admin Commands ACTIVADO")

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

# Controller to manage multiple bots
import json

STATUS_FILE = "status_config.json"

class BotController:
    def __init__(self):
        self.bots = []
        self.status_data = self.load_status()

    def register(self, bot):
        self.bots.append(bot)
        bot.controller = self # Inject controller into bot

    def load_status(self):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_status(self):
        with open(STATUS_FILE, 'w') as f:
            json.dump(self.status_data, f)

    async def broadcast_status(self, status_type: str, activity_text: str, message_text: str = None):
        """
        status_type: 'maintenance', 'active', 'shutdown'
        """
        # Define Status and Activity
        if status_type == 'maintenance':
            status = discord.Status.dnd
            activity = discord.Activity(type=discord.ActivityType.playing, name="🚧 Mantenimiento")
            embed_color = discord.Color.orange()
            title = "🚧 MANTENIMIENTO 🚧"
        elif status_type == 'shutdown':
            status = discord.Status.offline
            activity = discord.Activity(type=discord.ActivityType.playing, name="💤 Apagado")
            embed_color = discord.Color.red()
            title = "🔴 APAGADO 🔴"
        elif status_type == 'active':
            status = discord.Status.online
            activity = discord.Activity(type=discord.ActivityType.playing, name="✅ Activo")
            embed_color = discord.Color.green()
            title = "✅ EN LÍNEA ✅"
        else:
            # Custom or Default
            status = discord.Status.online
            activity = discord.Activity(type=discord.ActivityType.playing, name=activity_text)
            embed_color = discord.Color.blue()
            title = "📢 ACTUALIZACIÓN"

        # Apply to all bots
        for bot in self.bots:
            try:
                # 1. Update Presence
                if bot.is_ready():
                    await bot.change_presence(status=status, activity=activity)
                    print(f"🔄 [{bot.bot_name}] Estado actualizado a {status_type}")

                # 2. Send/Edit Announcement (if message provided OR if we are updating status)
                # We always want to update the persistent message if possible, even if message_text is None (status change)
                
                # Determine Channel ID based on Guild
                channel_id = None
                guild_key = str(bot.target_guild_id)
                if bot.target_guild_id == 1237573087013109811: # Zero
                    channel_id = int(os.getenv('ZEROP_STATUS_CHANNEL_ID', '1473927006520344626'))
                elif bot.target_guild_id == 1091109766237007992: # Iglesia
                    channel_id = int(os.getenv('IGLESIA_STATUS_CHANNEL_ID', '1471653028594581655'))
                
                if channel_id and bot.is_ready():
                    channel = bot.get_channel(channel_id)
                    if channel:
                        embed = discord.Embed(title=title, description=message_text if message_text else f"Estado: {activity.name}", color=embed_color)
                        embed.set_footer(text=f"Actualización Global • {bot.user.name}")
                        embed.timestamp = discord.utils.utcnow()

                        # Try to edit existing message
                        sent_message = None
                        last_msg_id = self.status_data.get(guild_key)
                        
                        if last_msg_id:
                            try:
                                msg = await channel.fetch_message(last_msg_id)
                                await msg.edit(embed=embed)
                                sent_message = msg
                                print(f"✏️ [{bot.bot_name}] Mensaje editado ({last_msg_id})")
                            except discord.NotFound:
                                print(f"⚠️ [{bot.bot_name}] Mensaje anterior no encontrado. Enviando nuevo.")
                            except Exception as e:
                                print(f"⚠️ [{bot.bot_name}] Error editando: {e}")

                        # If didn't edit, send new
                        if not sent_message and status_type != 'shutdown': # Don't send new message on shutdown if edit fails
                            sent_message = await channel.send(embed=embed)
                            print(f"Dg [{bot.bot_name}] Nuevo mensaje enviado ({sent_message.id})")
                        
                        if sent_message:
                            self.status_data[guild_key] = sent_message.id
                            self.save_status()

                    else:
                        print(f"⚠️ [{bot.bot_name}] No se encontró el canal de estado {channel_id}")
            except Exception as e:
                print(f"❌ Error actualizando {bot.bot_name}: {e}")

async def main_runner():
    server_config = load_server_config()
    
    # Initialize Controller
    controller = BotController()

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
            controller.register(bot) # Register to controller
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
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        print("\n🛑 Apagando el sistema... Actualizando estados...")
        await controller.broadcast_status('shutdown', 'Apagado', "El sistema se ha apagado o reiniciado.")

if __name__ == "__main__":
    try:
        asyncio.run(main_runner())
    except KeyboardInterrupt:
        pass
