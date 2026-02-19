import discord
from discord.ext import commands
from discord import app_commands
import os

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_admin(self, interaction: discord.Interaction) -> bool:
        # Check if user is in the admin list of the current guild
        admin_id_str = ""
        if interaction.guild_id == int(os.getenv('ZEROP_GUILD_ID', 0)):
            admin_id_str = os.getenv('ZEROP_ADMIN_USER_ID', '')
        elif interaction.guild_id == int(os.getenv('IGLESIA_GUILD_ID', 0)):
            admin_id_str = os.getenv('IGLESIA_ADMIN_USER_ID', '')
        
        # Also check global backup
        if not admin_id_str:
            admin_id_str = os.getenv('ADMIN_USER_ID', '')

        if not admin_id_str:
            return False

        admin_ids = [int(x.strip()) for x in admin_id_str.split(',') if x.strip()]
        return interaction.user.id in admin_ids

    @app_commands.command(name="estado", description="[ADMIN] Cambiar estado global del bot y anunciar")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Mantenimiento 🚧", value="mantenimiento"),
        app_commands.Choice(name="Activo ✅", value="active"),
        app_commands.Choice(name="Apagado 💤", value="shutdown"),
        app_commands.Choice(name="Personalizado 📢", value="custom")
    ])
    @app_commands.describe(mensaje="Mensaje para el anuncio (Opcional)", texto_actividad="Texto del estado (Solo para personalizado)")
    async def estado(self, interaction: discord.Interaction, tipo: app_commands.Choice[str], mensaje: str = None, texto_actividad: str = None):
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return

        if not hasattr(self.bot, 'controller'):
            await interaction.response.send_message("❌ Error crítico: El controlador de bots no está vinculado.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        status_type = tipo.value
        activity_text = texto_actividad if texto_actividad else "Comunidad Zero"

        # Broadcast update via controller
        await self.bot.controller.broadcast_status(status_type, activity_text, mensaje)

        await interaction.followup.send(f"✅ Estado global actualizado a **{tipo.name}** en todos los bots.", ephemeral=True)


    @commands.Cog.listener()
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Check if it's a Bridge Message (from Webhook)
        if message.webhook_id and message.content.startswith("[LINK_BYPASS]"):
            print(f"🌉 Bridge Message Detected in {message.channel}")
            # 2. Extract Data
            try:
                # Content format: [LINK_BYPASS] **Original:** <url>\n**Destino (Enc):** ||<base64>||
                import re
                import base64

                # Search for encoded part (inside || || or just the text)
                # We look for "Destino (Enc):" and then capture the content
                lines = message.content.split('\n')
                enc_line = next((line for line in lines if "Destino (Enc):" in line), None)
                
                final_url = None

                if enc_line:
                    print(f"   ↳ Encrypted line found: {enc_line}")
                    # Clean up wrappers like || or spaces
                    cleaned_enc = enc_line.replace("**Destino (Enc):**", "").replace("||", "").strip()
                    
                    try:
                        # Decode Base64
                        decoded_bytes = base64.b64decode(cleaned_enc)
                        final_url = decoded_bytes.decode('utf-8')
                        print(f"   ↳ Decoded URL: {final_url}")
                    except Exception as e:
                        print(f"Error decoding base64: {e}")

                # OLD FORMAT FALLBACK: Check for "Destino:" with explicit URL
                if not final_url:
                    dest_line = next((line for line in lines if "Destino:" in line), None)
                    if dest_line:
                        match = re.search(r'<(https?://[^>]+)>', dest_line)
                        if match:
                            final_url = match.group(1)
                
                if final_url:
                    # 3. Find User to DM
                    target_id = None
                    
                    # Check for explicit User ID in message: "**User:** 123456789"
                    user_line = next((line for line in lines if "User:" in line), None)
                    if user_line:
                        # Match numbers after "User:" (handling bolding or spaces)
                        match_user = re.search(r'User:.*?(\d+)', user_line)
                        if match_user:
                            target_id = int(match_user.group(1))
                            print(f"   ↳ Explicit Target User ID found: {target_id}")

                    # Fallback to Admin ID config
                    if not target_id:
                        admin_id_str = os.getenv('ADMIN_USER_ID', '') or os.getenv('ZEROP_ADMIN_USER_ID', '')
                        print(f"   ↳ Target Admin IDs (Fallback): {admin_id_str}")
                        if admin_id_str:
                            target_id = int(admin_id_str.split(',')[0].strip())
                    
                    if not target_id:
                        print("   ❌ No target user found.")
                        return

                    # Get user object
                    target_user = self.bot.get_user(target_id) or await self.bot.fetch_user(target_id)
                    
                    if target_user:
                        print(f"   ↳ Sending DM to {target_user}")
                        embed = discord.Embed(title="🔓 Link Desbloqueado", description=f"Aquí tienes tu link:\n\n👉 **[Clic para abrir]({final_url})**\n`{final_url}`", color=discord.Color.green())
                        embed.set_footer(text="Enviado desde ZeroBot Web Tools")
                        await target_user.send(embed=embed)
                        
                        await message.add_reaction("✅")
                    else:
                        print(f"   ❌ Could not find admin user {target_id}")

            except Exception as e:
                print(f"Error in Link Bridge: {e}")

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
