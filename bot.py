import os
from keep_alive import keep_alive
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from mcstatus import JavaServer
import discord
from discord.ext import tasks
from discord import app_commands

#############################################
# CONFIG
#############################################
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
UPDATE_MINUTES = int(os.getenv("UPDATE_MINUTES", "5"))
STATE_FILE = "guilds_state.json"

#############################################
# BOT SETUP
#############################################
intents = discord.Intents.default()
intents.guilds = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

#############################################
# UTILS
#############################################


# Remover códigos de color de Minecraft (ej: §a, §l, etc.)
def strip_minecraft_colors(text):
    if not text:
        return ""
    return re.sub(r"§[0-9A-FK-ORa-fk-or]", "", text)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


async def query(address):
    try:
        server = JavaServer.lookup(address)
        status = server.status()
        return status
    except:
        return None


#############################################
# EMBED BUILDER (con UTC-3)
#############################################

def build_embed(address, status):
    from datetime import datetime, timedelta

    # Hora UTC-3
    utc_now = datetime.utcnow()
    utc_minus3 = utc_now - timedelta(hours=3)

    # Color premium púrpura
    premium_color = discord.Color.from_rgb(120, 86, 255)

    # Separador premium
    separator = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    embed = discord.Embed(
        title="🌌 Estado del Servidor",
        description=f"**IP:** `{address}`\n{separator}",
        colour=premium_color,
        timestamp=utc_minus3
    )

    # -------------------------
    #   Servidor Offline
    # -------------------------
    if status is None:
        embed.add_field(
            name="❌ Servidor Offline",
            value=f"No responde o está apagado.\n{separator}",
            inline=False
        )
        embed.set_footer(text="Actualizado • UTC-3")
        return embed

    # =========================
    #        MOTD LIMPIO
    # =========================
    motd = status.description
    if isinstance(motd, dict):
        motd = motd.get("text") or str(motd)

    # quitar códigos §
    motd = strip_minecraft_colors(str(motd))

    # eliminar espacios extra al inicio
    motd_lines = motd.split("\n")
    motd_lines = [line.lstrip() for line in motd_lines]

    # Diferenciar líneas:
    if len(motd_lines) >= 2:
        line1 = f"        {motd_lines[0]}"            # HATORSMP en negrita
        line2 = f"       {motd_lines[1]}"                     # Seguime en kick...
        motd_lines = [line1, line2]
    # centrar
    max_len = max(len(line) for line in motd_lines)
    centered_lines = [line.center(max_len) for line in motd_lines]
    motd_centered = "\n".join(centered_lines)

    # MOTD con caja negra
    embed.add_field(
        name="⛏️ MOTD",
        value=f"```\n{motd_centered}\n```{separator}",
        inline=False
    )

    # =========================
    #        VERSIÓN
    # =========================
    version_clean = strip_minecraft_colors(
        getattr(status.version, "name", "Desconocida")
    )
    embed.add_field(
        name="🧩 Versión",
        value=f"**{version_clean}**",
        inline=True
    )

    # =========================
    #        JUGADORES
    # =========================
    online = getattr(status.players, "online", "?")
    maxp = getattr(status.players, "max", "?")
    embed.add_field(
        name="👥 Jugadores",
        value=f"**{online}** / {maxp}",
        inline=True
    )

    embed.set_footer(text="Actualizado • UTC-3")

    return embed






#############################################
# UPDATE LOOP
#############################################
@tasks.loop(minutes=UPDATE_MINUTES)
async def update_loop():
    await bot.wait_until_ready()

    state = load_state()

    for gid, data in state.items():
        address = data.get("address")
        channel_id = data.get("channel_id")
        if not address or not channel_id:
            continue

        try:
            channel = await bot.fetch_channel(channel_id)
        except:
            continue

        status = await query(address)
        embed = build_embed(address, status)

        msg_id = data.get("message_id")
        msg = None

        # Buscar mensaje existente
        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
            except:
                msg = None

        if msg:
            # Actualizar mensaje existente
            try:
                await msg.edit(embed=embed)
            except:
                pass
        else:
            # Crear mensaje nuevo
            sent = await channel.send(embed=embed)
            data["message_id"] = sent.id
            save_state(state)


#############################################
# ON READY
#############################################

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    await tree.sync()
    print("Comandos registrados.")

    if not update_loop.is_running():
        update_loop.start()


#############################################
# SLASH COMMANDS
#############################################

@tree.command(name="setip", description="Configurar la IP del servidor Minecraft")
async def setip(interaction: discord.Interaction, address: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Solo administradores.", ephemeral=True)
        return

    state = load_state()
    gid = str(interaction.guild.id)

    entry = state.get(gid, {})
    entry["address"] = address
    state[gid] = entry
    save_state(state)

    await interaction.response.send_message(f"IP configurada: `{address}`", ephemeral=True)


@tree.command(name="setchannel", description="Elegir el canal donde se publicará el estado")
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Solo administradores.", ephemeral=True)
        return

    state = load_state()
    gid = str(interaction.guild.id)

    entry = state.get(gid, {})
    entry["channel_id"] = channel.id
    entry.pop("message_id", None)
    state[gid] = entry
    save_state(state)

    await interaction.response.send_message(f"Canal configurado: {channel.mention}", ephemeral=True)


#############################################
# RUN
#############################################

if not DISCORD_TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN en .env")

keep_alive()

bot.run(DISCORD_TOKEN)
