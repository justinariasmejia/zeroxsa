import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import datetime
from dotenv import load_dotenv
from utils_db import load_server_config

load_dotenv()

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ **Cerrando ticket en 5 segundos...**", ephemeral=True)
        
        # Transcript Logic
        transcript_text = f"Transcripción del Ticket: {interaction.channel.name}\n"
        transcript_text += f"Cerrado por: {interaction.user.name} ({interaction.user.id})\n"
        transcript_text += f"Fecha: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        transcript_text += "-" * 50 + "\n\n"

        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            author = f"{msg.author.name} ({msg.author.id})"
            content = msg.content
            if msg.embeds:
                content += " [Embed]"
            if msg.attachments:
                content += f" [Adjuntos: {', '.join([a.url for a in msg.attachments])}]"
            
            transcript_text += f"[{timestamp}] {author}: {content}\n"

        # Send to Log Channel
        server_config = load_server_config()
        guild_conf = server_config.get(interaction.guild_id)
        
        log_channel_id = None
        if guild_conf:
            log_channel_id = guild_conf.get('ticket_log_channel_id')

        if log_channel_id:
            try:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    # Create file
                    with open("transcript.txt", "w", encoding="utf-8") as f:
                        f.write(transcript_text)
                    
                    file = discord.File("transcript.txt", filename=f"transcript-{interaction.channel.name}.txt")
                    
                    embed = discord.Embed(
                        title="🔒 Ticket Cerrado",
                        description=f"Ticket **{interaction.channel.name}** ha sido cerrado.",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now()
                    )
                    embed.add_field(name="Cerrado por", value=interaction.user.mention)
                    embed.add_field(name="Canal", value=interaction.channel.name)
                    
                    await log_channel.send(embed=embed, file=file)
                    
                    # Clean up file
                    os.remove("transcript.txt")
            except Exception as e:
                print(f"Error enviando log: {e}")

        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Reclamar Ticket", style=discord.ButtonStyle.success, emoji="🙋‍♂️", custom_id="btn_claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Update button
        button.disabled = True
        button.label = f"Reclamado por {interaction.user.display_name}"
        button.style = discord.ButtonStyle.secondary
        
        # Update Embed
        try:
            # We need to edit the message attached to this view.
            # interaction.message is the message containing the buttons.
            original_embed = interaction.message.embeds[0]
            
            # Add or update field
            # Check if field exists to avoid duplication if clicked multiple times (though button disabled prevents this usually)
            original_embed.add_field(name="👮‍♂️ Ticket encargado a", value=interaction.user.mention, inline=False)
            
            # Change color to indicate progress
            original_embed.color = discord.Color.gold()
            
            await interaction.message.edit(embed=original_embed, view=self)
            await interaction.response.send_message(f"✅ Has reclamado este ticket.", ephemeral=True)
            await interaction.channel.send(f"👮‍♂️ **Atención:** {interaction.user.mention} se ha encargado de este ticket.")

        except Exception as e:
            await interaction.response.send_message(f"Error actualizando el ticket: {e}", ephemeral=True)

class TicketTypeSelect(discord.ui.Select):
    def __init__(self, guild_id: int):
        options = [
            discord.SelectOption(label="Soporte Técnico", emoji="🛠️", description="Problemas con el servidor o el bot"),
            discord.SelectOption(label="Reportar Usuario", emoji="🚨", description="Reportar mal comportamiento"),
            discord.SelectOption(label="Dudas / Consultas", emoji="❓", description="Preguntas generales"),
            discord.SelectOption(label="Donaciones", emoji="💸", description="Ayuda al servidor"),
        ]

        # Conditional Option for ZERO Server
        # ID: 1237573087013109811
        if guild_id == 1237573087013109811:
             options.append(discord.SelectOption(label="Postulación a Staff", emoji="🛡️", description="Aplica para formar parte del equipo"))

        super().__init__(placeholder="Selecciona el motivo del ticket...", min_values=1, max_values=1, custom_id="select_ticket_type", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Determine role to ping based on selection
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            try:
                category = await guild.create_category("Tickets")
            except discord.Forbidden:
                await interaction.followup.send("⛔ Error: No tengo permisos para crear la categoría 'Tickets'.", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # Load Config
        server_config = load_server_config()
        guild_conf = server_config.get(interaction.guild_id)
        
        support_role_ids = []
        if guild_conf:
            ids = guild_conf.get('ticket_support_role_id')
            if isinstance(ids, list):
                support_role_ids = ids
            elif isinstance(ids, int):
                support_role_ids = [ids]

        # Priority 1: IDs from .env
        staff_roles = []
        if support_role_ids:
            for rid in support_role_ids:
                role = guild.get_role(rid)
                if role:
                    staff_roles.append(role)
        
        # Priority 2: Name search (Fallback if no IDs or IDs invalid)
        if not staff_roles:
             found = discord.utils.get(guild.roles, name="Staff") or discord.utils.get(guild.roles, name="Soporte")
             if found:
                 staff_roles.append(found)

        # Apply overwrites to all found roles
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_type = self.values[0]
        
        # Customize Channel Name & Message based on type
        if ticket_type == "Postulación a Staff":
            channel_name = f"postulacion-{interaction.user.name}"
            desc = f"Hola {interaction.user.mention},\n\nHas abierto un ticket de **Postulación** para unirte al Staff.\n\nPor favor, responde a las siguientes preguntas:\n1. ¿Edad?\n2. ¿Experiencia previa?\n3. ¿Por qué quieres unirte?\n\nUn administrador revisará tu solicitud pronto."
        else:
            channel_name = f"ticket-{interaction.user.name}"
            desc = f"Hola {interaction.user.mention},\n\nHas abierto un ticket por: **{ticket_type}**.\nUn miembro del equipo { ' '.join([r.mention for r in staff_roles]) if staff_roles else '@here' } te atenderá pronto.\n\nDescribe tu consulta detalladamente mientras esperas."

        try:
            channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        except Exception as e:
            await interaction.followup.send(f"Error creando el canal: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ **Ticket creado:** {channel.mention}", ephemeral=True)

        embed = discord.Embed(
            title=f"{ticket_type}",
            description=desc,
            color=discord.Color.gold() if ticket_type == "Postulación a Staff" else discord.Color.blue()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Usa los botones para gestionar el ticket")
        
        # Mention logic
        ping_content = f"{interaction.user.mention}"
        if staff_roles:
            ping_content += " " + " ".join([r.mention for r in staff_roles])
        else:
            ping_content += " @here"

        await channel.send(content=ping_content, embed=embed, view=TicketControlView())

class TicketView(discord.ui.View):
    def __init__(self, guild_id: int = None):
        super().__init__(timeout=None)
        # If no guild_id passed (e.g. at startup/persistence loading), we can't fully determine dynamic options easily 
        # without storing guild_id in custom_id or similar hacks. 
        # BUT: For persistent views, discord re-initializes them without args usually.
        # However, for the initial message sent via command, we have the ID.
        # For simplicity in this specific request, we default to 0 if None, 
        # avoiding the extra option on reboot if not handled, but strictly fulfilling the user request for the "menu".
        # To make it persistent properly with dynamic options per guild is complex.
        # We will assume this is primarily for the Setup command usage.
        self.add_item(TicketTypeSelect(guild_id or 0))

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_tickets", description="Admin: Configura el panel de tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        # Respond immediately to avoid timeout
        await interaction.response.send_message("✅ Panel de tickets desplegado.", ephemeral=True)
        
        embed = discord.Embed(
            title="🎫 Centro de Ayuda",
            description="Bienvenido al sistema de soporte.\n\nPor favor, **selecciona una categoría** en el menú de abajo para abrir un ticket y contactar con el Staff.",
            color=discord.Color.from_rgb(0, 191, 255) # Deep Sky Blue
        )
        embed.set_image(url="https://media.discordapp.net/attachments/100000000000000000/100000000000000001/ticket_banner.png")
        embed.set_footer(text="El mal uso de los tickets será sancionado.")

        try:
             # Pass Guild ID here!
             await interaction.channel.send(embed=embed, view=TicketView(guild_id=interaction.guild_id))
        except Exception as e:
             await interaction.followup.send(f"⚠️ Error al enviar el panel: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
