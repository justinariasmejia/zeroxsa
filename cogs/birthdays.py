import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import datetime
import os
from dotenv import load_dotenv
from utils_db import get_db_path, load_server_config

load_dotenv()
BIRTHDAY_CHANNEL_ID = os.getenv('BIRTHDAY_CHANNEL_ID')

class BirthdayModal(discord.ui.Modal, title="Registrar Cumpleaños 🎂"):
    day = discord.ui.TextInput(
        label="Día",
        placeholder="Ej: 15",
        min_length=1,
        max_length=2,
        required=True
    )
    month = discord.ui.TextInput(
        label="Mes",
        placeholder="Ej: 8 (Agosto)",
        min_length=1,
        max_length=2,
        required=True
    )
    year = discord.ui.TextInput(
        label="Año (Opcional)",
        placeholder="Ej: 2000",
        min_length=4,
        max_length=4,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = int(self.day.value)
            m = int(self.month.value)
            y = int(self.year.value) if self.year.value else None

            # Simple validation
            if not (1 <= m <= 12) or not (1 <= d <= 31):
                raise ValueError("Fecha inválida")
            
            # Check if valid date (e.g. Feb 30)
            datetime.date(2000, m, d) # Using leap year to allow Feb 29

        except ValueError:
            await interaction.response.send_message("❌ **Fecha inválida.** Por favor verifica el día y el mes.", ephemeral=True)
            return

        if not interaction.guild_id:
             await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO birthdays (user_id, day, month, year)
                VALUES (?, ?, ?, ?)
            """, (interaction.user.id, d, m, y))
            await db.commit()

        await interaction.response.send_message(f"✅ **¡Guardado!** Tu cumpleaños se ha registrado para el **{d}/{m}**.", ephemeral=True)

class BirthdayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Agregar/Editar Fecha", style=discord.ButtonStyle.success, emoji="🎂", custom_id="btn_bday_add")
    async def add_bday(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal())

    @discord.ui.button(label="Ver Próximos", style=discord.ButtonStyle.primary, emoji="🗓️", custom_id="btn_bday_view")
    async def view_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        today = datetime.date.today()
        
        if not interaction.guild_id:
             await interaction.followup.send("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return
        
        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user_id, day, month FROM birthdays") as cursor:
                all_bdays = await cursor.fetchall()

        if not all_bdays:
            await interaction.followup.send("📭 No hay cumpleaños registrados.", ephemeral=True)
            return

        # Calculate next occurrence
        upcoming = []
        for uid, d, m in all_bdays:
            try:
                this_year_bday = datetime.date(today.year, m, d)
                if this_year_bday < today:
                    next_bday = datetime.date(today.year + 1, m, d)
                else:
                    next_bday = this_year_bday
                
                days_until = (next_bday - today).days
                upcoming.append((uid, days_until, next_bday))
            except ValueError:
                continue # Skip invalid dates (leap years etc)

        # Sort by days until
        upcoming.sort(key=lambda x: x[1])
        upcoming = upcoming[:5] # Top 5

        desc = ""
        for uid, days, date_obj in upcoming:
            user = interaction.guild.get_member(uid)
            if not user:
                try:
                    user = await interaction.client.fetch_user(uid)
                except:
                    user = None
            
            name = f"**{user.display_name}**" if user else f"Usuario {uid}"
            
            if days == 0:
                time_str = "**¡ES HOY!** 🎉"
            elif days == 1:
                time_str = "Mañana ⏰"
            else:
                time_str = f"En {days} días"
            
            desc += f"• {name} - {date_obj.day}/{date_obj.month} ({time_str})\n"

        embed = discord.Embed(title="📅 Próximos Cumpleaños", description=desc or "Nadie cumple años pronto...", color=discord.Color.gold())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Borrar mis datos", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_bday_del")
    async def delete_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild_id:
             await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM birthdays WHERE user_id = ?", (interaction.user.id,))
            await db.commit()
        await interaction.response.send_message("🗑️ **Datos eliminados.** Ya no recibirás felicitaciones.", ephemeral=True)

    @discord.ui.button(label="Alertas", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="btn_bday_role")
    async def toggle_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_name = "Notificaciones de Cumpleaños"
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        
        if not role:
            # Create role if it doesn't exist (Requires Manage Roles)
            try:
                role = await interaction.guild.create_role(name=role_name, mentionable=True, color=discord.Color.gold())
            except discord.Forbidden:
                await interaction.response.send_message("⛔ No tengo permisos para crear/gestionar el rol de alertas.", ephemeral=True)
                return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"🔕 Te he quitado el rol {role.mention}.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"🔔 Te he dado el rol {role.mention}. ¡Te avisaré cuando haya pastel!", ephemeral=True)

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    @app_commands.command(name="setup_birthdays", description="Admin: Configura el panel de cumpleaños")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_birthdays(self, interaction: discord.Interaction):
        # Respond immediately
        await interaction.response.send_message("✅ Panel de cumpleaños configurado.", ephemeral=True)
        
        embed = discord.Embed(
            title="🎂 Sistema de Cumpleaños",
            description="¡No dejes que nadie olvide tu día especial! 🎉\n\n**🎂 Agregar/Editar Fecha**\nRegistra o actualiza tu cumpleaños.\n\n**🗓️ Ver Próximos**\nMira quién cumple años pronto.\n\n**🔔 Alertas**\nRole para recibir notificaciones.\n\n**❌ Borrar mis datos**\nElimina tu registro.",
            color=discord.Color.from_rgb(255, 105, 180) # Hot Pink
        )
        # Use a nice footer or thumbnail if desired
        try:
             await interaction.channel.send(embed=embed, view=BirthdayView())
        except Exception as e:
             await interaction.followup.send(f"⚠️ Error al enviar el panel: {e}", ephemeral=True)

    @app_commands.command(name="set_birthday_user", description="Admin: Establece el cumpleaños de otro usuario")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="Usuario a editar", day="Día (1-31)", month="Mes (1-12)", year="Año (Opcional)")
    async def set_birthday_user(self, interaction: discord.Interaction, user: discord.User, day: int, month: int, year: int = None):
        try:
            # Simple validation
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                raise ValueError("Fecha inválida")
            # Check leap year validity roughly
            datetime.date(2000, month, day)
            
            if not interaction.guild_id:
                 await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
                 return
            
            db_path = get_db_path(interaction.guild_id)

        except ValueError:
            await interaction.response.send_message(f"❌ Fecha inválida: {day}/{month}", ephemeral=True)
            return

        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO birthdays (user_id, day, month, year)
                VALUES (?, ?, ?, ?)
            """, (user.id, day, month, year))
            await db.commit()
        
        await interaction.response.send_message(f"✅ Cumpleaños de **{user.display_name}** establecido para el **{day}/{month}**.", ephemeral=True)

    @tasks.loop(hours=24)
    async def check_birthdays(self):
        server_config = load_server_config()
        today = datetime.date.today()

        # Loop through ALL guilds the bot is connected to
        for guild in self.bot.guilds:
            try:
                # 1. Check if we have config for this guild
                guild_conf = server_config.get(guild.id)
                if not guild_conf:
                    continue # No config for this guild, skip

                bday_channel_id = guild_conf.get('birthday_channel_id')
                if not bday_channel_id:
                    continue # No birthday channel configured, skip

                # 2. Get DB for this guild
                db_path = get_db_path(guild.id)
                if not os.path.exists(db_path):
                    continue

                async with aiosqlite.connect(db_path) as db:
                    async with db.execute("SELECT user_id FROM birthdays WHERE day = ? AND month = ?", (today.day, today.month)) as cursor:
                        birthday_users = await cursor.fetchall()
                
                if birthday_users:
                    channel = guild.get_channel(bday_channel_id)
                    
                    if channel:
                        # Get Role for Mention
                        role = discord.utils.get(guild.roles, name="Notificaciones de Cumpleaños")
                        role_mention = role.mention if role else "@here"

                        mentions = []
                        for (uid,) in birthday_users:
                            member = guild.get_member(uid)
                            if member:
                                mentions.append(member.mention)
                        
                        if mentions:
                            users_str = ", ".join(mentions)
                            await channel.send(f"🎉 {role_mention} **¡HOY ES UN DÍA ESPECIAL!** 🎉\n\nDeseadle un muy feliz cumpleaños a {users_str} 🎂🥳\n¡Que paséis un día genial!")
            except Exception as e:
                print(f"Error checking birthdays for guild {guild.name} ({guild.id}): {e}")

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Birthdays(bot))
