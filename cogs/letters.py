import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import datetime
import re
import os
from utils_db import get_db_path
from typing import Literal

# --- UI Components ---

class RecipientSelect(discord.ui.UserSelect):
    def __init__(self, is_anonymous: bool):
        super().__init__(placeholder="Busca y selecciona a la persona... ", min_values=1, max_values=1)
        self.is_anonymous = is_anonymous

    async def callback(self, interaction: discord.Interaction):
        # Check letter limit (Max 4)
        if not interaction.guild_id:
             await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)
        
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM letters WHERE sender_id = ?", (interaction.user.id,)) as cursor:
                count_row = await cursor.fetchone()
                current_count = count_row[0] if count_row else 0
        
        if current_count >= 4:
            await interaction.response.send_message("⛔ **Has alcanzado el límite de 4 cartas.**\n¡Deja algo de amor para los demás! 😉", ephemeral=True)
            return

        target_user = self.values[0]
        await interaction.response.send_modal(LetterModal(self.is_anonymous, target_user))

class RecipientView(discord.ui.View):
    def __init__(self, is_anonymous: bool):
        super().__init__(timeout=60)
        self.add_item(RecipientSelect(is_anonymous))

class LetterModal(discord.ui.Modal):
    def __init__(self, is_anonymous: bool, target_user: discord.User):
        title = "Escribiendo a: " + target_user.display_name
        super().__init__(title=title[:45])
        self.is_anonymous = is_anonymous
        self.target_user = target_user

    message = discord.ui.TextInput(
        label="Tu Mensaje",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe tu carta aquí...",
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sender_id = interaction.user.id
        sender_name = str(interaction.user)
        recipient_text = self.target_user.mention 
        message_text = self.message.value
        timestamp = datetime.datetime.now()

        if not interaction.guild_id:
             await interaction.followup.send("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT INTO letters (sender_id, sender_name, recipient, message, is_anonymous, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sender_id, sender_name, recipient_text, message_text, self.is_anonymous, timestamp))
            await db.commit()

        # Log logic
        from utils_db import load_server_config
        server_config = load_server_config()
        guild_conf = server_config.get(interaction.guild_id)
        
        recipients = []
        if guild_conf:
            recipients = guild_conf.get('log_recipients', [])

        if recipients:
            embed = discord.Embed(title="Nueva Carta Registrada 📨", color=discord.Color.orange())
            embed.add_field(name="De", value=f"{sender_name} (`{sender_id}`)", inline=True)
            embed.add_field(name="Para", value=f"{self.target_user.name} ({recipient_text})", inline=True)
            embed.add_field(name="Tipo", value="Anónima 🕵️" if self.is_anonymous else "Firmada ✍️", inline=True)
            embed.add_field(name="Mensaje", value=message_text, inline=False)
            embed.add_field(name="Servidor", value=f"{interaction.guild.name} ({interaction.guild_id})", inline=False)
            embed.timestamp = timestamp

            # Use bot to send logs
            for rid in recipients:
                try:
                    target = interaction.client.get_channel(rid) or interaction.client.get_user(rid)
                    if not target:
                        try:
                            target = await interaction.client.fetch_user(rid)
                        except:
                            continue
                    
                    if target:
                        await target.send(embed=embed)

                except Exception as e:
                    print(f"Error sending log to {rid}: {e}")

        confirm_embed = discord.Embed(
            title="¡Carta Guardada! 💌",
            description=f"Carta lista para **{self.target_user.display_name}**. Se enviará el 14.",
            color=discord.Color.green()
        )
        if self.is_anonymous:
            confirm_embed.set_footer(text="Tu identidad está segura 🤫")
        
        await interaction.followup.send(embed=confirm_embed, ephemeral=True)

class MailboxView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar Carta Anónima", style=discord.ButtonStyle.secondary, emoji="🕵️", custom_id="btn_anon")
    async def send_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("¿A quién quieres enviar la carta? Selecciona abajo 👇", view=RecipientView(is_anonymous=True), ephemeral=True)

    @discord.ui.button(label="Enviar Carta Firmada", style=discord.ButtonStyle.primary, emoji="✍️", custom_id="btn_signed")
    async def send_signed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("¿A quién quieres enviar la carta? Selecciona abajo 👇", view=RecipientView(is_anonymous=False), ephemeral=True)

    @discord.ui.button(label="Cartas", style=discord.ButtonStyle.danger, emoji="💌", custom_id="btn_release", row=1)
    async def release_letters_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
        admin_ids = [aid.strip() for aid in (ADMIN_USER_ID or "").split(',') if aid.strip()]
        if str(interaction.user.id) not in admin_ids:
            await interaction.response.send_message(f"⛔ ¡Solo el administrador designado puede liberar las cartas!", ephemeral=True)
            return

        await interaction.response.defer()
        
        if not interaction.guild_id:
             await interaction.followup.send("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)
        
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT sender_name, recipient, message, is_anonymous FROM letters") as cursor:
                letters = await cursor.fetchall()
                
        if not letters:
            await interaction.followup.send("¡No hay cartas en el buzón! 😢", ephemeral=True)
            return

        await interaction.followup.send(f"🚀 Procesando {len(letters)} cartas...", ephemeral=True)
        
        sent_count = 0
        failed_count = 0

        for sender_name, recipient, message, is_anonymous in letters:
            title = "💌 Carta de San Valentín"
            color = discord.Color.red() if is_anonymous else discord.Color.pink()
            author_text = "Admirador Secreto 🕵️" if is_anonymous else sender_name
            
            embed = discord.Embed(title=title, description=message, color=color)
            embed.add_field(name="Para", value=recipient, inline=True)
            embed.add_field(name="De", value=author_text, inline=True)
            
            match = re.search(r'<@!?(\d+)>', recipient)
            if match:
                user_id = int(match.group(1))
                try:
                    user = interaction.client.get_user(user_id) or await interaction.client.fetch_user(user_id)
                    if user:
                        dm_embed = embed.copy()
                        dm_embed.description = f"**¡Has recibido una carta!**\n\n{message}"
                        await user.send(embed=dm_embed)
                        sent_count += 1
                    else:
                        failed_count += 1
                except:
                    failed_count += 1
            else:
                failed_count += 1

        await interaction.channel.send("✅ **¡Se han enviado todas las cartas a sus correspondientes destinos!** 📬💕")
        await interaction.followup.send(f"📊 **Reporte de entrega:**\n✅ Entregadas: {sent_count}\n❌ Fallidas: {failed_count}", ephemeral=True)

class Letters(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_mailbox", description="Admin: Configura el buzón de cartas")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_mailbox(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📬 Buzón de San Valentín",
            description="¡El amor y la amistad están en el aire! 💕\n\nUsa los botones de abajo para escribir una carta.\nPodrás elegir si quieres que sea **Anónima** o **Firmada**.\n\nEl día 14, se liberarán todas las cartas aquí mismo.📅",
            color=discord.Color.from_rgb(255, 105, 180)
        )
        embed.set_image(url="https://media.discordapp.net/attachments/100000000000000000/100000000000000000/valentine_banner.png")
        embed.set_footer(text="¡Exprésate libremente! (Máx 4 cartas por persona)")
        
        await interaction.channel.send(embed=embed, view=MailboxView())
        await interaction.response.send_message("Buzón configurado correctamente.", ephemeral=True)

    @app_commands.command(name="reset_mailbox", description="Admin: Borra TODAS las cartas del buzón")
    async def reset_mailbox(self, interaction: discord.Interaction):
        ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
        admin_ids = [aid.strip() for aid in (ADMIN_USER_ID or "").split(',') if aid.strip()]
        if str(interaction.user.id) not in admin_ids:
            await interaction.response.send_message(f"⛔ ¡Solo el administrador designado puede reiniciar el buzón!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild_id:
             await interaction.followup.send("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM letters")
            await db.commit()
            await db.execute("VACUUM")
            await db.commit()
        
        await interaction.followup.send("🗑️ **¡Buzón vaciado!** Se han eliminado todas las cartas.", ephemeral=True)

    @app_commands.command(name="view_letters", description="Admin: Ver cartas guardadas (Filtros opcionales)")
    @app_commands.describe(user="Filtrar por usuario", tipo="Filtrar por tipo (Enviadas/Recibidas)")
    async def view_letters(self, interaction: discord.Interaction, user: discord.User = None, tipo: Literal['Enviadas', 'Recibidas'] = None):
        try:
            ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
            # Check per-server admins
            from utils_db import load_server_config
            server_config = load_server_config()
            guild_conf = server_config.get(interaction.guild_id)
            
            allowed_ids = []
            if ADMIN_USER_ID:
                allowed_ids.extend([aid.strip() for aid in ADMIN_USER_ID.split(',') if aid.strip()])
            if guild_conf and guild_conf.get('admin_ids'):
                 allowed_ids.extend([str(x) for x in guild_conf.get('admin_ids')])
                 
            if str(interaction.user.id) not in allowed_ids:
                await interaction.response.send_message(f"⛔ ¡Solo administradores!", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            # Query
            query = "SELECT id, sender_name, recipient, message, is_anonymous, timestamp, sender_id FROM letters"
            params = []
            conditions = []
            
            if user:
                if tipo == 'Enviadas':
                    conditions.append("sender_id = ?")
                    params.append(user.id)
                elif tipo == 'Recibidas':
                    conditions.append("recipient LIKE ?")
                    params.append(f"%{user.id}%")
                else:
                    # Both
                    conditions.append("(sender_id = ? OR recipient LIKE ?)")
                    params.extend([user.id, f"%{user.id}%"])
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            if not interaction.guild_id:
                 await interaction.followup.send("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
                 return

            db_path = get_db_path(interaction.guild_id)
            
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(query, tuple(params)) as cursor:
                    letters = await cursor.fetchall()
                    
            if not letters:
                await interaction.followup.send("📭 No se encontraron cartas.", ephemeral=True)
                return

            sent_letters = []
            received_letters = []

            # Categorize results if no specific type selected or if user not specified (though type needs user logically usually, but let's handle it)
            # If user selected a type, all letters are of that type.
            
            for row in letters:
                # row[6] is sender_id
                # If we filtered by 'Enviadas', they are all sent.
                # If we filtered by 'Recibidas', they are all received.
                # If no filter, we categorize.
                if user:
                    if row[6] == user.id:
                        sent_letters.append(row)
                    else:
                        received_letters.append(row)
                else:
                    # If no user specified, put everything in one list (could be huge)
                    sent_letters.append(row) 

            response_text = ""
            
            def format_list(letter_list, title_emoji):
                section = ""
                for l_id, s_name, recip, msg, is_anon, ts, sid in letter_list:
                    anon_tag = "🕵️" if is_anon else "✍️"
                    msg = msg or "[Sin mensaje]"
                    short_msg = (msg[:50] + '..') if len(msg) > 50 else msg
                    ts_str = str(ts).split('.')[0]
                    section += f"🆔 `{l_id}` | De: {s_name} {anon_tag} | Para: {recip}\n📝 \"{short_msg}\"\n-------------------\n"
                return section

            if user:
                # If user + type='Enviadas' -> sent_letters has content, received_letters is empty
                if tipo == 'Enviadas':
                     if sent_letters:
                        response_text += f"**📤 Cartas Enviadas por {user.display_name}:**\n"
                        response_text += format_list(sent_letters, "📤")
                elif tipo == 'Recibidas':
                     if received_letters:
                        response_text += f"**📥 Cartas Recibidas por {user.display_name}:**\n"
                        response_text += format_list(received_letters, "📥")
                else:
                    # Show both
                    if sent_letters:
                        response_text += f"**📤 Cartas Enviadas por {user.display_name}:**\n"
                        response_text += format_list(sent_letters, "📤")
                    if received_letters:
                        response_text += f"\n**📥 Cartas Recibidas por {user.display_name}:**\n"
                        response_text += format_list(received_letters, "📥")
            else:
                response_text = f"**📂 Todas las Cartas ({len(letters)}):**\n"
                response_text += format_list(letters, "📂")

            # Add tip
            if response_text:
                response_text += "\n\n💡 **Tip:** Usa `/read_letter <id>` para descargar/leer la carta completa."
            else:
                 await interaction.followup.send("📭 No se encontraron cartas con ese filtro.", ephemeral=True)
                 return

            if len(response_text) > 1900:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                for chunk in chunks:
                    await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.followup.send(response_text, ephemeral=True)
                    
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error interno: {e}", ephemeral=True)

    @app_commands.command(name="read_letter", description="Admin: Leer/Descargar el contenido completo de una carta")
    @app_commands.describe(letter_id="El ID de la carta")
    async def read_letter(self, interaction: discord.Interaction, letter_id: int):
        ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
        # We also need to check per-server admins if configured
        from utils_db import load_server_config
        server_config = load_server_config()
        guild_conf = server_config.get(interaction.guild_id)
        
        allowed_ids = []
        if ADMIN_USER_ID:
            allowed_ids.extend([aid.strip() for aid in ADMIN_USER_ID.split(',') if aid.strip()])
        if guild_conf and guild_conf.get('admin_ids'):
             allowed_ids.extend([str(x) for x in guild_conf.get('admin_ids')])
             
        if str(interaction.user.id) not in allowed_ids:
            await interaction.response.send_message(f"⛔ ¡Solo administradores!", ephemeral=True)
            return

        if not interaction.guild_id:
             await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)
        
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT sender_name, recipient, message, is_anonymous, timestamp FROM letters WHERE id = ?", (letter_id,)) as cursor:
                row = await cursor.fetchone()
                
        if not row:
            await interaction.response.send_message(f"❌ No encontré carta con ID `{letter_id}`.", ephemeral=True)
            return

        sender_name, recipient, message, is_anonymous, timestamp = row
        anon_str = "SÍ" if is_anonymous else "NO"
        
        # Create text file content
        content = f"""=== CARTA #{letter_id} ===
Fecha: {timestamp}
De: {sender_name}
Para: {recipient}
Anónima: {anon_str}
=======================

{message}

=======================
"""
        import io
        file = discord.File(io.BytesIO(content.encode('utf-8')), filename=f"carta_{letter_id}.txt")
        
        embed = discord.Embed(title=f"📜 Visualizando Carta #{letter_id}", description=message[:4000], color=discord.Color.blue())
        embed.add_field(name="De", value=sender_name, inline=True)
        embed.add_field(name="Para", value=recipient, inline=True)
        embed.set_footer(text="Archivo adjunto con el contenido completo.")
        
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="delete_letter", description="Admin: Borrar una carta por ID")
    @app_commands.describe(letter_id="El ID de la carta a borrar")
    async def delete_letter(self, interaction: discord.Interaction, letter_id: int):
        ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
        admin_ids = [aid.strip() for aid in (ADMIN_USER_ID or "").split(',') if aid.strip()]
        if str(interaction.user.id) not in admin_ids:
            await interaction.response.send_message(f"⛔ ¡Solo administradores!", ephemeral=True)
            return

        if not interaction.guild_id:
             await interaction.response.send_message("❌ Error: No se pudo identificar el servidor.", ephemeral=True)
             return

        db_path = get_db_path(interaction.guild_id)

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT id FROM letters WHERE id = ?", (letter_id,)) as cursor:
                if not await cursor.fetchone():
                    await interaction.response.send_message(f"❌ No encontré ninguna carta con ID `{letter_id}` en este servidor.", ephemeral=True)
                    return
            
            await db.execute("DELETE FROM letters WHERE id = ?", (letter_id,))
            await db.commit()

        await interaction.response.send_message(f"🗑️ Carta `{letter_id}` eliminada correctamente de la base de datos de {interaction.guild.name}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Letters(bot))
