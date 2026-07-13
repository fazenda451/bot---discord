import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import json
import re
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

REACTIONS = ["✅", "❌", "🕟"]

COLOR_BLUE   = 0x5865F2
COLOR_GREEN  = 0x57F287
COLOR_RED    = 0xED4245
COLOR_YELLOW = 0xFEE75C

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

    embed = discord.Embed(
        title=f"🎮  {activity.upper()}",
        description=(
            "Reage em cada hora com a tua disponibilidade:\n\n"
            "✅ **Presente**\n"
            "❌ **Não estou**\n"
            "🕟 **Demoro 15min máximo**"
        ),
        color=COLOR_BLUE,
        timestamp=now,
    )
    embed.set_footer(text=f"Horário • {now.strftime('%d/%m/%Y')}")
    await channel.send(embed=embed)

    for h in hours:
        msg = await channel.send(f"🕐  **{h}H**")
        for emoji in REACTIONS:
            try:
                await msg.add_reaction(emoji)
            except (discord.NotFound, discord.HTTPException):
                pass
            await asyncio.sleep(0.5)


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

    if hora_inicio == -1:
        hora_inicio = (now.hour + 1) % 24
    if hora_fim == -1:
        hora_fim = (hora_inicio + 4) % 24

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


# ── /editar ─────────────────────────────────────
@bot.tree.command(
    name="editar",
    description="Adiciona ou remove horas de um horário já postado no canal",
)
@app_commands.describe(
    adicionar="Horas a adicionar separadas por espaço  (ex: 21 22)",
    remover="Horas a remover separadas por espaço  (ex: 16 17)",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_editar(
    interaction: discord.Interaction,
    adicionar: str = "",
    remover: str = "",
):
    await interaction.response.defer(ephemeral=True)

    if not adicionar.strip() and not remover.strip():
        await interaction.followup.send(
            embed=discord.Embed(
                description="❌ Tens de indicar horas para adicionar ou remover!",
                color=COLOR_RED,
            ),
            ephemeral=True,
        )
        return

    try:
        horas_add = [int(h) for h in adicionar.split() if h] if adicionar.strip() else []
        horas_rem = [int(h) for h in remover.split() if h] if remover.strip() else []
    except ValueError:
        await interaction.followup.send(
            embed=discord.Embed(description="❌ Horas inválidas!", color=COLOR_RED),
            ephemeral=True,
        )
        return

    # Encontra mensagens de hora no canal
    hour_msgs: dict[int, discord.Message] = {}
    async for msg in interaction.channel.history(limit=60):
        if msg.author == bot.user and "🕐" in msg.content:
            match = re.search(r"\*\*(\d+)H\*\*", msg.content)
            if match:
                h = int(match.group(1))
                hour_msgs[h] = msg

    removed, added = [], []

    # Remove horas
    for h in horas_rem:
        if h in hour_msgs:
            try:
                await hour_msgs[h].delete()
                removed.append(h)
            except discord.Forbidden:
                pass

    # Adiciona horas
    for h in sorted(horas_add):
        if h not in hour_msgs:
            msg = await interaction.channel.send(f"🕐  **{h}H**")
            for emoji in REACTIONS:
                try:
                    await msg.add_reaction(emoji)
                except (discord.NotFound, discord.HTTPException):
                    pass
                await asyncio.sleep(0.5)
            added.append(h)

    lines = []
    if added:
        lines.append(f"➕ Adicionadas: {', '.join(f'**{h}H**' for h in added)}")
    if removed:
        lines.append(f"➖ Removidas: {', '.join(f'**{h}H**' for h in removed)}")
    if not lines:
        lines.append("Nenhuma alteração feita.")

    await interaction.followup.send(
        embed=discord.Embed(
            title="✏️ Horário Editado",
            description="\n".join(lines),
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )


# ── /resumo ─────────────────────────────────────
@bot.tree.command(
    name="resumo",
    description="Mostra quem reagiu em cada hora do horário atual",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_resumo(interaction: discord.Interaction):
    await interaction.response.defer()

    # Encontra mensagens de hora no canal (mais antigas primeiro)
    hour_msgs: list[discord.Message] = []
    async for msg in interaction.channel.history(limit=60):
        if msg.author == bot.user and "🕐" in msg.content:
            match = re.search(r"\*\*(\d+)H\*\*", msg.content)
            if match:
                hour_msgs.append(msg)

    if not hour_msgs:
        await interaction.followup.send(
            embed=discord.Embed(
                description="❌ Nenhum horário encontrado neste canal.",
                color=COLOR_YELLOW,
            ),
            ephemeral=True,
        )
        return

    hour_msgs.reverse()  # mais antiga primeiro

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    embed = discord.Embed(
        title="📊  Resumo de Disponibilidade",
        color=COLOR_BLUE,
        timestamp=now,
    )

    for msg in hour_msgs:
        match = re.search(r"\*\*(\d+)H\*\*", msg.content)
        hora = match.group(1) if match else "?"
        field_lines = []

        for reaction in msg.reactions:
            if str(reaction.emoji) in REACTIONS:
                users = [u async for u in reaction.users() if not u.bot]
                if users:
                    nomes = ", ".join(f"**{u.display_name}**" for u in users)
                    field_lines.append(f"{reaction.emoji} {nomes}")

        embed.add_field(
            name=f"🕐 {hora}H",
            value="\n".join(field_lines) if field_lines else "*Sem reações ainda*",
            inline=False,
        )

    embed.set_footer(text=f"Resumo gerado às {now.strftime('%H:%M')}")
    await interaction.followup.send(embed=embed)


# ── /auto ────────────────────────────────────────
@bot.tree.command(
    name="auto",
    description="Adiciona um agendamento automático diário",
)
@app_commands.describe(
    id="ID único para este agendamento  (ex: farm, raid, boss)",
    atividade="Nome da atividade  (ex: FARMAR LIXO)",
    hora_inicio="Primeira hora do horário  (ex: 16)",
    hora_fim="Última hora do horário  (ex: 20)",
    hora_post="Hora a que o bot publica a mensagem  (ex: 15)",
)
@app_commands.default_permissions(administrator=True)
async def slash_auto(
    interaction: discord.Interaction,
    id: str,
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

    if hora_inicio > hora_fim:
        await interaction.response.send_message(
            embed=discord.Embed(description="❌ A hora de início tem de ser menor que a hora de fim!", color=COLOR_RED),
            ephemeral=True,
        )
        return

    cfg = load_config()
    schedules: list = cfg.get("auto_schedules", [])

    # Remove agendamento com mesmo ID se existir
    schedules = [s for s in schedules if s["id"] != id]
    schedules.append({
        "id": id,
        "channel_id": interaction.channel_id,
        "activity": atividade,
        "hours": list(range(hora_inicio, hora_fim + 1)),
        "post_hour": hora_post,
    })

    cfg["auto_schedules"] = schedules
    save_config(cfg)
    bot._auto_schedules = schedules

    horas_str = " · ".join(f"{h}H" for h in range(hora_inicio, hora_fim + 1))

    embed = discord.Embed(
        title="⏰  Agendamento Adicionado",
        color=COLOR_GREEN,
    )
    embed.add_field(name="🆔 ID",         value=f"`{id}`",                 inline=True)
    embed.add_field(name="📌 Atividade",  value=f"**{atividade}**",        inline=True)
    embed.add_field(name="⏱️ Publica às", value=f"**{hora_post}H**",       inline=True)
    embed.add_field(name="🕐 Horários",   value=horas_str,                 inline=False)
    embed.add_field(name="📢 Canal",      value=interaction.channel.mention, inline=False)
    embed.set_footer(text=f"Total de agendamentos: {len(schedules)} • Usa /parar id:{id} para cancelar")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /parar ───────────────────────────────────────
@bot.tree.command(name="parar", description="Para um ou todos os agendamentos automáticos")
@app_commands.describe(id="ID do agendamento a parar — deixa vazio para parar TODOS")
@app_commands.default_permissions(administrator=True)
async def slash_parar(interaction: discord.Interaction, id: str = ""):
    cfg = load_config()
    schedules: list = cfg.get("auto_schedules", [])

    if not schedules:
        await interaction.response.send_message(
            embed=discord.Embed(description="ℹ️ Não há agendamentos ativos.", color=COLOR_YELLOW),
            ephemeral=True,
        )
        return

    if id:
        novos = [s for s in schedules if s["id"] != id]
        removidos = len(schedules) - len(novos)
        msg = f"🛑 Agendamento `{id}` parado." if removidos else f"❌ Não encontrei nenhum agendamento com ID `{id}`."
        cor = COLOR_RED if removidos else COLOR_YELLOW
    else:
        novos = []
        removidos = len(schedules)
        msg = f"🛑 Todos os {removidos} agendamentos foram parados."
        cor = COLOR_RED

    cfg["auto_schedules"] = novos
    save_config(cfg)
    bot._auto_schedules = novos

    await interaction.response.send_message(
        embed=discord.Embed(description=msg, color=cor),
        ephemeral=True,
    )


# ── /status ──────────────────────────────────────
@bot.tree.command(name="status", description="Mostra todos os agendamentos automáticos ativos")
@app_commands.default_permissions(manage_messages=True)
async def slash_status(interaction: discord.Interaction):
    cfg = load_config()
    schedules: list = cfg.get("auto_schedules", [])

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if not schedules:
        embed = discord.Embed(
            title="📊  Estado do Bot",
            description="Nenhum agendamento automático configurado.\nUsa `/auto` para criar um!",
            color=COLOR_YELLOW,
        )
    else:
        embed = discord.Embed(
            title=f"📊  Agendamentos Ativos ({len(schedules)})",
            color=COLOR_GREEN,
        )
        for s in schedules:
            channel = bot.get_channel(s["channel_id"])
            horas_str = " · ".join(f"{h}H" for h in s["hours"])
            embed.add_field(
                name=f"🎮 {s['activity']}  •  ID: `{s['id']}`",
                value=(
                    f"📢 Canal: {channel.mention if channel else '?'}\n"
                    f"🕐 Horários: {horas_str}\n"
                    f"⏱️ Publica às: **{s['post_hour']}H**"
                ),
                inline=False,
            )

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
        title="📅  Bot de Horários — Comandos",
        description="Gere os horários das tuas atividades com reações de disponibilidade.",
        color=COLOR_BLUE,
    )
    embed.add_field(
        name="</horario>",
        value="Posta um horário.\n`atividade` `hora_inicio` `hora_fim`",
        inline=False,
    )
    embed.add_field(
        name="</editar>",
        value="Edita o horário já postado.\n`adicionar: 21 22` ou `remover: 16 17`",
        inline=False,
    )
    embed.add_field(
        name="</resumo>",
        value="Mostra quem reagiu em cada hora.",
        inline=False,
    )
    embed.add_field(
        name="</auto>",
        value="Adiciona agendamento automático diário.\n`id` `atividade` `hora_inicio` `hora_fim` `hora_post`",
        inline=False,
    )
    embed.add_field(
        name="</parar>",
        value="Para um agendamento pelo `id`, ou todos se não deres ID.",
        inline=False,
    )
    embed.add_field(
        name="</status>",
        value="Mostra todos os agendamentos ativos.",
        inline=False,
    )
    embed.add_field(
        name="</limpar>",
        value="Apaga mensagens do canal.",
        inline=False,
    )
    embed.add_field(
        name="🎭 Reações",
        value="✅ Presente • ❌ Não estou • 🕟 Demoro 15min",
        inline=False,
    )
    embed.set_footer(text="Apenas admins podem usar /auto e /parar.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════
#  PREFIX COMMANDS
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
    """Forca ressincronizacao dos slash commands neste servidor."""
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
#  TASK — AUTO SCHEDULE (suporta múltiplos)
# ═══════════════════════════════════════════════
@tasks.loop(minutes=1)
async def check_auto_schedule():
    schedules: list = getattr(bot, "_auto_schedules", [])
    if not schedules:
        return

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    for s in schedules:
        if now.hour == s["post_hour"] and now.minute == 0:
            channel = bot.get_channel(s["channel_id"])
            if channel:
                await post_schedule(channel, s["activity"], s["hours"])


# ═══════════════════════════════════════════════
#  EVENTOS
# ═══════════════════════════════════════════════
@bot.event
async def on_ready():
    cfg = load_config()

    # Migração: suporte ao formato antigo (auto_schedule singular)
    if "auto_schedule" in cfg and "auto_schedules" not in cfg:
        old = cfg.pop("auto_schedule")
        old["id"] = "principal"
        cfg["auto_schedules"] = [old]
        save_config(cfg)

    bot._auto_schedules = cfg.get("auto_schedules", [])

    # Sync global
    try:
        synced = await bot.tree.sync()
        print(f"[OK] {len(synced)} slash commands sincronizados globalmente")
    except Exception as e:
        print(f"[ERR] Erro ao sincronizar: {e}")

    check_auto_schedule.start()
    print(f"[OK] Bot online: {bot.user} (ID: {bot.user.id})")
    print(f"[TZ] Fuso horario: {TIMEZONE}")
    print(f"[SCH] {len(bot._auto_schedules)} agendamento(s) carregado(s)")
    print("-" * 40)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Sem permissao para usar este comando.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        pass
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
