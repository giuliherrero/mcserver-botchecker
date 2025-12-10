import os
from keep_alive import keep_alive
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from mcstatus import JavaServer
import discord
from discord.ext import tasks
from discord import app_commands
import tinydb
from tinydb import TinyDB, Query

#############################################
# CONFIG
#############################################
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
UPDATE_MINUTES = int(os.getenv("UPDATE_MINUTES", "1"))
STATE_FILE = "db.json"

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

def get_db():
    # TinyDB se encargará de crear y manejar el archivo STATE_FILE
    return TinyDB(STATE_FILE)

def load_state():
    db = get_db()
    # Cargamos todos los documentos de la DB y los convertimos a un diccionario
    # El formato es {guild_id: {data}, ...}
    
    # TinyDB guarda cada guild como un documento, ej: {'gid': '12345', 'address': 'ip'}
    
    # Para ser compatible con tu código anterior de JSON:
    # Retornamos un diccionario donde la clave es el ID del servidor
    data = {}
    for entry in db.all():
        data[entry['gid']] = {k: v for k, v in entry.items() if k != 'gid'}
    return data

def save_state(state):
    db = get_db()
    db.truncate() # Borramos todo para escribir el nuevo estado completo (simplificación)
    
    # Escribimos cada guild como un documento en la DB
    for gid, data in state.items():
        doc = {'gid': gid} # La clave 'gid' es necesaria para TinyDB
        doc.update(data)
        db.insert(doc)
    
    # Cerrar la conexión
    db.close()

#############################################
# EMBED BUILDER (con UTC)
#############################################

def build_embed(address, status):
    from datetime import datetime

    # Hora UTC-3
    utc_now = datetime.utcnow()
    

    # Color premium púrpura
    premium_color = discord.Color.from_rgb(120, 86, 255)

    # Separador premium
    separator = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    embed = discord.Embed(
        title="🌌 Estado del Servidor",
        description=f"**IP:** `{address}`\n{separator}",
        colour=premium_color,
        timestamp=utc_now
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
        embed.set_footer(text="Actualizado • UTC")
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
        value=f"****Java: 1.18.0 — 1.21.10\nBedrock: 1.21.90 — 1.21.130****",
        inline=True
    )

    # =========================
    #        JUGADORES
    # =========================
    # Definimos online y maxp aquí, antes de usarlas
    online = getattr(status.players, "online", 0) # Si no hay valor, asumimos 0
    maxp = getattr(status.players, "max", "?")
    
    embed.add_field(
        name="👥 Jugadores",
        value=f"**{online}** / {maxp}",
        inline=True
    )
    

    embed.set_footer(text="Actualizado • UTC")

    return embed






#############################################
# UPDATE LOOP
#############################################
@tasks.loop(minutes=UPDATE_MINUTES)
async def update_loop():
    await bot.wait_until_ready()

    state = load_state()

    # --- 1. Obtener la IP principal para el estado del bot ---
    # Asumiremos la IP del primer servidor configurado como la principal
    # para mostrar en el estado global del bot.
    main_address = None
    if state:
        first_guild_data = next(iter(state.values()), None)
        if first_guild_data:
            main_address = first_guild_data.get("address")
    
    # --- 2. Consultar el estado y establecer la actividad ---
    if main_address:
        status = await query(main_address)
        
        if status:
            online = getattr(status.players, "online", 0)
            maxp = getattr(status.players, "max", "?")
            activity_text = f"Jugadores {online}/{maxp}"
            activity_type = discord.ActivityType.watching # "Viendo" (Watching) es un buen tipo de actividad
        else:
            activity_text = f"Servidor {main_address} OFFLINE"
            activity_type = discord.ActivityType.playing # "Jugando" (Playing) se usa a menudo para offline
            
        # Establecer la actividad del bot
        activity = discord.Activity(name=activity_text, type=activity_type)
        await bot.change_presence(activity=activity)

    # --- 3. Bucle de actualización de embeds (código existente) ---
    for gid, data in state.items():
        address = data.get("address")
        channel_id = data.get("channel_id")
        # ... (resto del código de actualización del embed) ...

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
            
            # --- MANEJO DE ERROR CRÍTICO ---
            except discord.NotFound:
                # El mensaje fue borrado. Lo eliminamos del estado
                # para que se cree uno nuevo en el siguiente paso (else).
                print(f"Error: Mensaje {msg_id} no encontrado. Creando uno nuevo.")
                data.pop("message_id", None)
                save_state(state) # Guardar el estado sin el ID
                continue # Saltamos a la siguiente iteración

            except:
                pass # Manejar otros errores de edición silenciosamente (como permisos)
        
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
    # Sincroniza los comandos slash con Discord
    await tree.sync() 
    
    print(f"Bot conectado como {bot.user}")
    
    # ---------------------------------------------
    # 1. SOLUCIÓN: Ejecutar el bucle de actualización INMEDIATAMENTE
    # ---------------------------------------------
    if not update_loop.is_running():
        update_loop.start()
        
        # ---------------------------------------------
        # 2. SOLUCIÓN: Forzar la primera ejecución de inmediato
        # ---------------------------------------------
        # Ejecutamos la función asíncrona directamente una vez para la actualización inicial
        # Esto actualiza el Rich Presence y el embed sin esperar el temporizador.
        await update_loop() 
        
    print("Tareas iniciadas.")


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

# ... (dentro de la sección SLASH COMMANDS) ...

@tree.command(name="help", description="Muestra comandos de configuración e información.")
async def help_command(interaction: discord.Interaction):
    app_id = bot.application_id or bot.user.id # Obtener el ID de la aplicación

    # Permisos básicos necesarios: Leer, Enviar, Embed Links (y Comandos de Aplicación)
    permissions_value = 2147518480 # Administrador: 8, solo mensajes y comandos: 2147518480

    # Generar el enlace de invitación
    invite_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={app_id}&"
        f"permissions={permissions_value}&scope=bot%20applications.commands"
    )

    embed = discord.Embed(
        title="📘 Ayuda del Bot de Estado de Minecraft",
        description="Este bot te permite monitorear el estado de un servidor de Minecraft y publicar el estado en un canal específico, actualizándolo automáticamente.",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="⚙️ Comandos de Configuración (Admin)",
        value=(
            "`/setip <address>`: Configura la IP del servidor (ej: play.ejemplo.com).\n"
            "`/setchannel <canal>`: Configura el canal para publicar el mensaje de estado (el bot lo enviará ahí).\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔗 Enlace de Invitación",
        value=f"[Invita el Bot a tu Servidor]({invite_url})",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True) # Solo el usuario lo ve


#############################################
# RUN
#############################################

if not os.getenv("DISCORD_TOKEN"): # <- Verificar directamente la variable de entorno
    raise RuntimeError("Falta DISCORD_TOKEN en .env")

keep_alive() 

# Usar os.getenv() para correr el bot, no la variable local
bot.run(os.getenv("DISCORD_TOKEN"))