import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import json
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════
#  CONFIGURAÇÃO
# ═══════════════════════════════════════════════
TOKEN    = os.getenv("DISCORD_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Lisbon")
CONFIG_FILE = "schedule_config.json"

REACTIONS = ["✅", "❌", "🕟", "🅿️"]

# Cores dos embeds
COLOR_BLUE   = 0x5865F2   # Cabeçalho
COLOR_GREEN  = 0x57F287   # Sucesso
COLOR_RED    = 0xED4245   # Erro
COLOR_YELLOW = 0xFEE75C   # Aviso
COLOR_DARK   = 0x2B2D31   # Hora individual

# ═══════════════════════════════════════════════
#  SETUP
# ═══════════════════════════════════════════════
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ═══════════════════════════════════════════════
#  PERSISTÊNCIA (JSON)
# ═══════════════════════════════════════════════
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════
#  HELPER — POSTAR HORÁRIO
# ═══════════════════════════════════════════════
async def post_schedule(channel: discord.TextChannel, activity: str, hours: list[int]):
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # ── Embed de cabeçalho ──────────────────────
    embed = discord.Embed(
        title=f"🎮  {activity.upper()}",
        description=(
            "Reage em cada hora com a tua disponibilidade:\n\n"
            "✅ **Presente**\n"
            "❌ **Não estou**\n"
            "🕟 **Demoro 15min máximo**\n"
            "🅿️ **Promessa**"
        ),
        color=COLOR_BLUE,
        timestamp=now,
    )
    embed.set_footer(
        text=f"Horário • {now.strftime('%d/%m/%Y')}",
        icon_url="https://cdn.discordapp.com/emojis/1234567890.png",
    )
    await channel.send(embed=embed)

    # ── Uma mensagem por hora ────────────────────
    for h in hours:
        msg = await channel.send(f"🕐  **{h}H**")
        for emoji in REACTIONS:
            try:
                await msg.add_reaction(emoji)
            except (discord.NotFound, discord.HTTPException):
                pass
            await asyncio.sleep(0.5)   # respeita rate-limit


# ═══════════════════════════════════════════════
#  SLASH COMMANDS
# ═══════════════════════════════════════════════

# ── /horario ────────────────────────────────────
@bot.tree.command(
    name="horario",
    description="Posta um horário de atividade com reações por hora",
)
@app_commands.describe(
    atividade="Nome da atividade  (ex: FARMAR LIXO)",
    hora_inicio="Hora de início  (ex: 16) — opcional, padrão: próxima hora",
    hora_fim="Hora de fim  (ex: 20) — opcional, padrão: início + 4",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_horario(
    interaction: discord.Interaction,
    atividade: str,
    hora_inicio: int = -1,
    hora_fim: int = -1,
):
    await interaction.response.defer(ephemeral=True)

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # Padrões automáticos
    if hora_inicio == -1:
        hora_inicio = (now.hour + 1) % 24
    if hora_fim == -1:
        hora_fim = (hora_inicio + 4) % 24

    # Valida intervalo
    if hora_inicio > hora_fim:
        await interaction.followup.send(
            embed=discord.Embed(
                description="❌ A hora de início tem de ser menor que a hora de fim!",
                color=COLOR_RED,
            ),
            ephemeral=True,
        )
        return

    hours_list = list(range(hora_inicio, hora_fim + 1))
    await post_schedule(interaction.channel, atividade, hours_list)

    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Horário **{atividade}** postado! ({hora_inicio}H → {hora_fim}H)",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )


# ── /auto ────────────────────────────────────────
@bot.tree.command(
    name="auto",
    description="Configura o envio automático diário do horário",
)
@app_commands.describe(
    atividade="Nome da atividade  (ex: FARMAR LIXO)",
    hora_inicio="Primeira hora do horário  (ex: 16)",
    hora_fim="Última hora do horário  (ex: 20)",
    hora_post="Hora a que o bot publica a mensagem  (ex: 15)",
)
@app_commands.default_permissions(administrator=True)
async def slash_auto(
    interaction: discord.Interaction,
    atividade: str,
    hora_inicio: int,
    hora_fim: int,
    hora_post: int,
):
    if not (0 <= hora_inicio <= 23 and 0 <= hora_fim <= 23 and 0 <= hora_post <= 23):
        await interaction.response.send_message(
            embed=discord.Embed(description="❌ Horas devem estar entre 0 e 23.", color=COLOR_RED),
            ephemeral=True,
        )
        return

    cfg = load_config()
    cfg["auto_schedule"] = {
        "channel_id": interaction.channel_id,
        "activity": atividade,
        "hours": list(range(hora_inicio, hora_fim + 1)),
        "post_hour": hora_post,
    }
    save_config(cfg)
    bot._auto_schedule = cfg["auto_schedule"]

    embed = discord.Embed(
        title="⏰  Agendamento Automático Ativado",
        color=COLOR_GREEN,
    )
    embed.add_field(name="📌 Atividade",  value=f"**{atividade}**",               inline=True)
    embed.add_field(name="🕐 Horários",   value=f"**{hora_inicio}H → {hora_fim}H**", inline=True)
    embed.add_field(name="📢 Canal",      value=interaction.channel.mention,       inline=True)
    embed.add_field(name="⏱️ Publica às", value=f"**{hora_post}H todos os dias**",  inline=False)
    embed.set_footer(text="Usa /parar para cancelar o agendamento.")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /parar ───────────────────────────────────────
@bot.tree.command(name="parar", description="Para o agendamento automático")
@app_commands.default_permissions(administrator=True)
async def slash_parar(interaction: discord.Interaction):
    cfg = load_config()
    if "auto_schedule" not in cfg:
        await interaction.response.send_message(
            embed=discord.Embed(description="ℹ️ Não há nenhum agendamento ativo.", color=COLOR_YELLOW),
            ephemeral=True,
        )
        return

    cfg.pop("auto_schedule", None)
    save_config(cfg)
    bot._auto_schedule = None

    await interaction.response.send_message(
        embed=discord.Embed(description="🛑 Agendamento automático parado.", color=COLOR_RED),
        ephemeral=True,
    )


# ── /status ──────────────────────────────────────
@bot.tree.command(name="status", description="Mostra o estado atual do agendamento automático")
@app_commands.default_permissions(manage_messages=True)
async def slash_status(interaction: discord.Interaction):
    cfg = load_config()
    sch = cfg.get("auto_schedule")

    if not sch:
        embed = discord.Embed(
            title="📊  Estado do Bot",
            description="Nenhum agendamento automático configurado.",
            color=COLOR_YELLOW,
        )
    else:
        channel = bot.get_channel(sch["channel_id"])
        embed = discord.Embed(
            title="📊  Estado do Bot",
            color=COLOR_GREEN,
        )
        embed.add_field(name="✅ Estado",     value="**Ativo**",                          inline=True)
        embed.add_field(name="📌 Atividade",  value=f"**{sch['activity']}**",             inline=True)
        embed.add_field(name="📢 Canal",      value=channel.mention if channel else "?",  inline=True)
        horas_str = " • ".join(f"{h}H" for h in sch["hours"])
        embed.add_field(name="🕐 Horários",   value=horas_str,                            inline=False)
        embed.add_field(name="⏱️ Publica às", value=f"**{sch['post_hour']}H**",           inline=True)

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    embed.set_footer(text=f"Agora: {now.strftime('%H:%M')} • {TIMEZONE}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /limpar ──────────────────────────────────────
@bot.tree.command(name="limpar", description="Apaga mensagens recentes do canal")
@app_commands.describe(quantidade="Número de mensagens a apagar (padrão: 50, máx: 100)")
@app_commands.default_permissions(manage_messages=True)
async def slash_limpar(interaction: discord.Interaction, quantidade: int = 50):
    quantidade = min(max(quantidade, 1), 100)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=quantidade)
    await interaction.followup.send(
        embed=discord.Embed(
            description=f"🗑️  **{len(deleted)}** mensagens apagadas.",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )


# ── /ajuda ───────────────────────────────────────
@bot.tree.command(name="ajuda", description="Mostra todos os comandos do bot")
async def slash_ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📅  Bot de Horários",
        description="Gere os horários das tuas atividades com reações de disponibilidade.",
        color=COLOR_BLUE,
    )
    embed.add_field(
        name="</horario>",
        value=(
            "Posta um horário manualmente.\n"
            "`atividade` → nome da atividade\n"
            "`horas` → horas separadas por espaço *(opcional)*\n"
            "Ex: `atividade: FARMAR LIXO` `horas: 16 17 18 19 20`"
        ),
        inline=False,
    )
    embed.add_field(
        name="</auto>",
        value=(
            "Configura envio automático diário.\n"
            "`atividade` `hora_inicio` `hora_fim` `hora_post`"
        ),
        inline=False,
    )
    embed.add_field(name="</parar>",  value="Para o agendamento automático.",  inline=False)
    embed.add_field(name="</status>", value="Mostra o estado do agendamento.", inline=False)
    embed.add_field(name="</limpar>", value="Apaga mensagens do canal.",        inline=False)
    embed.add_field(
        name="🎭 Reações",
        value="✅ Presente • ❌ Não estou • 🕟 Demoro 15min • 🅿️ Promessa",
        inline=False,
    )
    embed.set_footer(text="Apenas admins podem usar /auto e /parar.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════
#  PREFIX COMMANDS (backup rápido)
# ═══════════════════════════════════════════════
@bot.command(name="limpar", aliases=["clear"])
@commands.has_permissions(manage_messages=True)
async def prefix_limpar(ctx, quantidade: int = 50):
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=min(quantidade, 100))
    await ctx.send(f"Apagadas {len(deleted)} mensagens.", delete_after=4)


@bot.command(name="sync")
@commands.is_owner()
async def prefix_sync(ctx):
    """Força ressincronização dos slash commands neste servidor."""
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ {len(synced)} comandos sincronizados! Faz Ctrl+R no Discord.", delete_after=10)
    except Exception as e:
        await ctx.send(f"Erro: {e}", delete_after=8)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass


# ═══════════════════════════════════════════════
#  TASK — AUTO SCHEDULE
# ═══════════════════════════════════════════════
@tasks.loop(minutes=1)
async def check_auto_schedule():
    cfg = getattr(bot, "_auto_schedule", None)
    if not cfg:
        return

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if now.hour == cfg["post_hour"] and now.minute == 0:
        channel = bot.get_channel(cfg["channel_id"])
        if channel:
            await post_schedule(channel, cfg["activity"], cfg["hours"])


# ═══════════════════════════════════════════════
#  EVENTOS
# ═══════════════════════════════════════════════
@bot.event
async def on_ready():
    # Carrega config persistente
    cfg = load_config()
    bot._auto_schedule = cfg.get("auto_schedule", None)

    # Sincroniza slash commands em todos os servidores automaticamente
    total = 0
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            total += len(synced)
            print(f"[OK] {len(synced)} comandos sincronizados em: {guild.name}")
        except Exception as e:
            print(f"[ERR] Erro ao sincronizar em {guild.name}: {e}")

    check_auto_schedule.start()
    print(f"[OK] Bot online: {bot.user} (ID: {bot.user.id})")
    print(f"[TZ] Fuso horario: {TIMEZONE}")
    print(f"[OK] {total} comandos sincronizados no total")
    print("-" * 40)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Sem permissao para usar este comando.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        pass  # ignora comandos desconhecidos
    else:
        print(f"Erro: {error}")


# ═══════════════════════════════════════════════
#  INICIAR
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    if not TOKEN:
        print("[ERR] DISCORD_TOKEN nao encontrado no .env!")
        exit(1)
    bot.run(TOKEN)
