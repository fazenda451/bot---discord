import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import json
import re
import shutil
import time
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════
#  CONFIGURAÇÃO
# ═══════════════════════════════════════════════
TOKEN    = os.getenv("DISCORD_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Lisbon")
CONFIG_FILE = "schedule_config.json"
BACKUP_DIR = "config_backups"
LATEST_BACKUP_FILE = "schedule_config.latest.bak"
MAX_BACKUPS = 50
BACKUP_MIN_INTERVAL = 1800

REACTIONS = ["✅", "❌", "🕟"]

MONTHS_PT = [
    "",
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

_backup_last_at = 0.0

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
def is_config_usable() -> bool:
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        if os.path.getsize(CONFIG_FILE) == 0:
            return False
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def restore_config_from_backup() -> bool:
    if os.path.exists(LATEST_BACKUP_FILE):
        try:
            with open(LATEST_BACKUP_FILE, "r", encoding="utf-8") as f:
                json.load(f)
            shutil.copy2(LATEST_BACKUP_FILE, CONFIG_FILE)
            print(f"[BAK] Config restaurado de {LATEST_BACKUP_FILE}")
            return True
        except (json.JSONDecodeError, OSError):
            pass

    if not os.path.isdir(BACKUP_DIR):
        return False

    backups = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.endswith(".json")),
        reverse=True,
    )
    for name in backups:
        path = os.path.join(BACKUP_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
            shutil.copy2(path, CONFIG_FILE)
            print(f"[BAK] Config restaurado de {path}")
            return True
        except (json.JSONDecodeError, OSError):
            continue
    return False


def ensure_config_available():
    if is_config_usable():
        return
    restore_config_from_backup()


def update_latest_backup():
    if os.path.exists(CONFIG_FILE) and is_config_usable():
        shutil.copy2(CONFIG_FILE, LATEST_BACKUP_FILE)


def create_timestamped_backup(force: bool = False):
    global _backup_last_at
    if not is_config_usable():
        return

    now_ts = time.time()
    if not force and now_ts - _backup_last_at < BACKUP_MIN_INTERVAL:
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    tz = pytz.timezone(TIMEZONE)
    stamp = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"schedule_config_{stamp}.json")
    shutil.copy2(CONFIG_FILE, dest)
    _backup_last_at = now_ts

    backups = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.endswith(".json")),
        reverse=True,
    )
    for old in backups[MAX_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass

    print(f"[BAK] Backup criado: {dest}")


def load_config() -> dict:
    ensure_config_available()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    update_latest_backup()
    create_timestamped_backup()


def get_tz_now() -> datetime:
    return datetime.now(pytz.timezone(TIMEZONE))


def get_guild_participation_history(cfg: dict, guild_id: int) -> list:
    return cfg.get("participation_history", {}).get(str(guild_id), [])


def record_participation_history(
    cfg: dict,
    guild_id: int,
    channel_id: int,
    atividade: str,
    participants: list[int],
    resumo_msg_id: int,
    closed_at: float | None = None,
):
    if "participation_history" not in cfg:
        cfg["participation_history"] = {}

    key = str(guild_id)
    history = cfg["participation_history"].get(key, [])

    for entry in history:
        if entry.get("resumo_msg_id") == resumo_msg_id:
            entry["participants"] = participants
            entry["atividade"] = atividade
            cfg["participation_history"][key] = history
            save_config(cfg)
            return

    history.insert(0, {
        "resumo_msg_id": resumo_msg_id,
        "channel_id": channel_id,
        "atividade": atividade,
        "closed_at": closed_at or time.time(),
        "participants": participants,
    })
    cfg["participation_history"][key] = history[:500]
    save_config(cfg)


def filter_history_by_month(history: list, year: int, month: int) -> list:
    tz = pytz.timezone(TIMEZONE)
    filtered = []
    for entry in history:
        closed_at = entry.get("closed_at")
        if not closed_at:
            continue
        dt = datetime.fromtimestamp(closed_at, tz=tz)
        if dt.year == year and dt.month == month:
            filtered.append(entry)
    return filtered


def count_participations_by_member(history: list) -> dict[int, int]:
    counts: dict[int, int] = {}
    for entry in history:
        for uid in entry.get("participants", []):
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def resolve_month_year(mes: int, ano: int) -> tuple[int, int, str | None]:
    now = get_tz_now()
    year = ano if ano > 0 else now.year
    month = mes if mes > 0 else now.month

    if not 1 <= month <= 12:
        return year, month, "❌ O mês deve estar entre 1 e 12."
    if year < 2020 or year > now.year + 1:
        return year, month, "❌ Ano inválido."
    return year, month, None


def format_member_display(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    if member:
        return member.mention
    return f"<@{user_id}>"


# ═══════════════════════════════════════════════
#  HELPER — POSTAR HORÁRIO
# ═══════════════════════════════════════════════
async def post_schedule(
    channel: discord.TextChannel,
    hours: list[int],
    role: discord.Role | None = None,
    activity: str = "",
):
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%d/%m")

    # Título do embed: se tiver atividade usa a atividade, senão usa a data
    title_str = f"🎮  {activity.upper()}" if activity else f"🗓️  {date_str}"

    # ── Embed de cabeçalho ──────────
    embed = discord.Embed(
        title=title_str,
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

    # ── Uma mensagem por hora com reações ──────
    for h in hours:
        msg = await channel.send(f"🕐  **{h}H**")
        for emoji in REACTIONS:
            try:
                await msg.add_reaction(emoji)
            except (discord.NotFound, discord.HTTPException):
                pass
            await asyncio.sleep(0.5)

    # ── Mensagem final de votos ─────────────────
    mention = role.mention if role else ""
    await channel.send(f"VOTEM FILHOS DA PUTA {mention}".strip())


# ═══════════════════════════════════════════════
#  SLASH COMMANDS
# ═══════════════════════════════════════════════

# ── /horario ────────────────────────────────────
@bot.tree.command(
    name="horario",
    description="Posta o horário do dia com reações por hora",
)
@app_commands.describe(
    atividade="Nome da atividade (ex: FARMAR LIXO)",
    hora_inicio="Hora de início  (ex: 16) — opcional, padrão: próxima hora",
    hora_fim="Hora de fim  (ex: 23) — opcional, padrão: início + 4",
    cargo="Cargo a mencionar no final",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_horario(
    interaction: discord.Interaction,
    atividade: str,
    hora_inicio: int = -1,
    hora_fim: int = -1,
    cargo: discord.Role | None = None,
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
    await post_schedule(interaction.channel, hours_list, cargo, atividade)

    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Horário postado! ({hora_inicio}H → {hora_fim}H)",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )


# ── /participacao ────────────────────────────────
@bot.tree.command(
    name="participacao",
    description="Inicia uma verificação de presença para uma atividade",
)
@app_commands.describe(
    atividade="Nome da atividade (ex: Treino, Reunião)",
    tempo="Tempo de duração em minutos (opcional, padrão: 15)",
)
async def slash_participacao(
    interaction: discord.Interaction,
    atividade: str,
    tempo: int = 15,
):
    await interaction.response.defer(ephemeral=True)

    if tempo <= 0:
        await interaction.followup.send(
            embed=discord.Embed(description="❌ O tempo deve ser maior que 0 minutos.", color=COLOR_RED),
            ephemeral=True,
        )
        return

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    # Embed Inicial de Participação Aberta
    embed = discord.Embed(
        title=f"📝 Participação: {atividade.upper()}",
        description=f"Reage com ✅ para confirmares a tua presença nesta atividade!\n\n⏳ **Tempo restante:** {tempo} minutos",
        color=COLOR_BLUE,
    )
    embed.set_footer(text=f"A participação fecha automaticamente às {(now + timedelta(minutes=tempo)).strftime('%H:%M')}.")
    
    # Envia a mensagem no canal público
    channel = interaction.channel
    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")

    # Guardar informação da participação para resiliência a quedas do bot
    end_timestamp = now.timestamp() + (tempo * 60)
    cfg = load_config()
    cfg["active_participation"] = {
        "msg_id": msg.id,
        "channel_id": channel.id,
        "atividade": atividade,
        "end_time": end_timestamp
    }
    save_config(cfg)

    # Confirmação efêmera para quem iniciou o comando
    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Participação para **{atividade}** iniciada no canal por {tempo} minutos!",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )

    # Agenda a finalização da participação
    asyncio.create_task(fechar_participacao_task(msg.id, channel.id, atividade, end_timestamp))


def format_resumo_participacao(atividade: str, users: list) -> str:
    if users:
        nomes_lista = "\n".join(
            f"- {u.mention if hasattr(u, 'mention') else f'<@{u.id}>'}"
            for u in users
        )
        return (
            f"📋 **Resumo da Atividade ({atividade}):**\n"
            f"Os seguintes membros participaram:\n{nomes_lista}"
        )
    return (
        f"📋 **Resumo da Atividade ({atividade}):**\n"
        f"Ninguém confirmou a presença a tempo."
    )


def get_closed_participations(cfg: dict, channel_id: int) -> list:
    return cfg.get("closed_participations", {}).get(str(channel_id), [])


def save_closed_participation(cfg: dict, channel_id: int, entry: dict):
    if "closed_participations" not in cfg:
        cfg["closed_participations"] = {}
    key = str(channel_id)
    entries = cfg["closed_participations"].get(key, [])
    entries.insert(0, entry)
    cfg["closed_participations"][key] = entries[:10]
    save_config(cfg)


def find_closed_participation(cfg: dict, channel_id: int, atividade: str | None = None) -> dict | None:
    entries = get_closed_participations(cfg, channel_id)
    if not entries:
        return None
    if atividade:
        atividade_lower = atividade.lower()
        for entry in entries:
            if entry.get("atividade", "").lower() == atividade_lower:
                return entry
        return None
    return entries[0]


async def find_resumo_message(channel: discord.TextChannel, atividade: str | None = None) -> discord.Message | None:
    async for msg in channel.history(limit=50):
        if msg.author != bot.user or not msg.content.startswith("📋 **Resumo da Atividade"):
            continue
        if atividade:
            match = re.search(r"Resumo da Atividade \((.+?)\):", msg.content)
            if not match or match.group(1).lower() != atividade.lower():
                continue
        return msg
    return None


def parse_participant_ids_from_resumo(content: str) -> list[int]:
    return [int(uid) for uid in re.findall(r"<@!?(\d+)>", content)]


async def fechar_participacao_task(msg_id: int, channel_id: int, atividade: str, end_timestamp: float):
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).timestamp()
    wait_time = end_timestamp - now
    
    if wait_time > 0:
        await asyncio.sleep(wait_time)

    channel = bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return

    try:
        # Puxa a mensagem atualizada para ler as reações
        updated_msg = await channel.fetch_message(msg_id)
        
        # Encontra a reação ✅ e os utilizadores correspondentes
        react = discord.utils.get(updated_msg.reactions, emoji="✅")
        users = []
        if react:
            async for user in react.users():
                if not user.bot:
                    users.append(user)
        
        # Edita o Embed para fechar a participação
        embed_fechado = discord.Embed(
            title=f"📝 Participação: {atividade.upper()} [FECHADA]",
            description="A janela de participação para esta atividade terminou.",
            color=COLOR_RED,
        )
        embed_fechado.set_footer(text="Participação encerrada.")
        await updated_msg.edit(embed=embed_fechado)
        
        # Tenta limpar as reações para ninguém mais poder clicar
        try:
            await updated_msg.clear_reactions()
        except discord.Forbidden:
            pass
        
        # Cria a mensagem final de resumo com lista (não-apagável)
        resumo_msg = await channel.send(format_resumo_participacao(atividade, users))

        cfg = load_config()
        closed_at = datetime.now(tz).timestamp()
        save_closed_participation(cfg, channel_id, {
            "resumo_msg_id": resumo_msg.id,
            "atividade": atividade,
            "participants": [u.id for u in users],
            "closed_at": closed_at,
        })

        if channel.guild:
            record_participation_history(
                cfg,
                channel.guild.id,
                channel_id,
                atividade,
                [u.id for u in users],
                resumo_msg.id,
                closed_at,
            )
        
    except discord.NotFound:
        print(f"Mensagem de participação {msg_id} não foi encontrada para encerramento.")
    except Exception as e:
        print(f"Erro ao fechar participação: {e}")
    finally:
        # Remove a participação ativa da persistência
        cfg = load_config()
        if "active_participation" in cfg and cfg["active_participation"].get("msg_id") == msg_id:
            cfg.pop("active_participation", None)
            save_config(cfg)


# ── /add ─────────────────────────────────────────
@bot.tree.command(
    name="add",
    description="Adiciona um membro à participação depois de fechada",
)
@app_commands.describe(
    membro="Membro a adicionar à lista de participantes",
    atividade="Nome da atividade (opcional, usa a mais recente se omitido)",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_add(
    interaction: discord.Interaction,
    membro: discord.Member,
    atividade: str = "",
):
    await interaction.response.defer(ephemeral=True)

    cfg = load_config()
    channel = interaction.channel
    atividade = atividade.strip()
    closed = find_closed_participation(cfg, channel.id, atividade or None)

    resumo_msg = None
    atividade_nome = atividade

    if closed:
        atividade_nome = closed["atividade"]
        try:
            resumo_msg = await channel.fetch_message(closed["resumo_msg_id"])
        except discord.NotFound:
            closed = None

    if not resumo_msg:
        resumo_msg = await find_resumo_message(channel, atividade or None)
        if not resumo_msg:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Nenhuma participação fechada encontrada neste canal.",
                    color=COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        if not atividade_nome:
            match = re.search(r"Resumo da Atividade \((.+?)\):", resumo_msg.content)
            atividade_nome = match.group(1) if match else "Atividade"

    if closed:
        participant_ids = list(closed.get("participants", []))
    else:
        participant_ids = parse_participant_ids_from_resumo(resumo_msg.content)

    if membro.id in participant_ids:
        await interaction.followup.send(
            embed=discord.Embed(
                description=f"ℹ️ {membro.mention} já está na lista de participantes.",
                color=COLOR_YELLOW,
            ),
            ephemeral=True,
        )
        return

    participant_ids.append(membro.id)
    guild = interaction.guild
    users = []
    for uid in participant_ids:
        user = guild.get_member(uid) or interaction.client.get_user(uid)
        if user:
            users.append(user)
        else:
            users.append(discord.Object(id=uid))

    await resumo_msg.edit(content=format_resumo_participacao(atividade_nome, users))

    cfg = load_config()
    entries = get_closed_participations(cfg, channel.id)
    updated = False
    for entry in entries:
        if entry.get("resumo_msg_id") == resumo_msg.id:
            entry["participants"] = participant_ids
            updated = True
            break
    if not updated:
        save_closed_participation(cfg, channel.id, {
            "resumo_msg_id": resumo_msg.id,
            "atividade": atividade_nome,
            "participants": participant_ids,
        })
    else:
        if "closed_participations" not in cfg:
            cfg["closed_participations"] = {}
        cfg["closed_participations"][str(channel.id)] = entries
        save_config(cfg)

    if interaction.guild:
        record_participation_history(
            load_config(),
            interaction.guild.id,
            channel.id,
            atividade_nome,
            participant_ids,
            resumo_msg.id,
        )

    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ {membro.mention} adicionado à participação **{atividade_nome}**.",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )


# ── /ranking ─────────────────────────────────────
@bot.tree.command(
    name="ranking",
    description="Mostra quem mais participou nas atividades do mês",
)
@app_commands.describe(
    mes="Mês (1-12, opcional — padrão: mês atual)",
    ano="Ano (opcional — padrão: ano atual)",
)
async def slash_ranking(
    interaction: discord.Interaction,
    mes: int = 0,
    ano: int = 0,
):
    await interaction.response.defer()

    year, month, error = resolve_month_year(mes, ano)
    if error:
        await interaction.followup.send(
            embed=discord.Embed(description=error, color=COLOR_RED),
            ephemeral=True,
        )
        return

    cfg = load_config()
    history = filter_history_by_month(
        get_guild_participation_history(cfg, interaction.guild.id),
        year,
        month,
    )
    counts = count_participations_by_member(history)

    if not counts:
        await interaction.followup.send(
            embed=discord.Embed(
                description=f"ℹ️ Sem participações registadas em **{MONTHS_PT[month]} de {year}**.",
                color=COLOR_YELLOW,
            ),
            ephemeral=True,
        )
        return

    ranking = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, count) in enumerate(ranking[:15]):
        prefix = medals[i] if i < 3 else f"**{i + 1}.**"
        lines.append(f"{prefix} {format_member_display(interaction.guild, uid)} — **{count}** participações")

    embed = discord.Embed(
        title=f"🏆 Ranking de Participação — {MONTHS_PT[month].capitalize()} {year}",
        description="\n".join(lines),
        color=COLOR_BLUE,
        timestamp=get_tz_now(),
    )
    embed.set_footer(text=f"{len(history)} atividades registadas neste mês")
    await interaction.followup.send(embed=embed)


# ── /presenca ────────────────────────────────────
@bot.tree.command(
    name="presenca",
    description="Mostra quantas vezes um membro participou num mês",
)
@app_commands.describe(
    membro="Membro a consultar (opcional — padrão: tu)",
    mes="Mês (1-12, opcional — padrão: mês atual)",
    ano="Ano (opcional — padrão: ano atual)",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_presenca(
    interaction: discord.Interaction,
    membro: discord.Member | None = None,
    mes: int = 0,
    ano: int = 0,
):
    await interaction.response.defer(ephemeral=True)

    target = membro or interaction.user
    year, month, error = resolve_month_year(mes, ano)
    if error:
        await interaction.followup.send(
            embed=discord.Embed(description=error, color=COLOR_RED),
            ephemeral=True,
        )
        return

    cfg = load_config()
    history = filter_history_by_month(
        get_guild_participation_history(cfg, interaction.guild.id),
        year,
        month,
    )

    count = 0
    atividades = []
    for entry in history:
        if target.id in entry.get("participants", []):
            count += 1
            atividades.append(entry.get("atividade", "Atividade"))

    month_name = MONTHS_PT[month]
    if count == 0:
        description = (
            f"{target.mention} não participou em nenhuma atividade "
            f"em **{month_name} de {year}**."
        )
    elif count == 1:
        description = (
            f"{target.mention} participou **1 vez** em **{month_name} de {year}**."
        )
    else:
        description = (
            f"{target.mention} participou **{count} vezes** em **{month_name} de {year}**."
        )

    embed = discord.Embed(
        title="📈 Presença do Membro",
        description=description,
        color=COLOR_GREEN if count else COLOR_YELLOW,
        timestamp=get_tz_now(),
    )

    if atividades:
        recent = atividades[:10]
        embed.add_field(
            name="Atividades",
            value="\n".join(f"• {name}" for name in recent),
            inline=False,
        )
        if len(atividades) > 10:
            embed.set_footer(text=f"+ {len(atividades) - 10} atividades adicionais")

    await interaction.followup.send(embed=embed)


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

    hour_msgs: dict[int, discord.Message] = {}
    async for msg in interaction.channel.history(limit=60):
        if msg.author == bot.user and "🕐" in msg.content:
            match = re.search(r"\*\*(\d+)H\*\*", msg.content)
            if match:
                h = int(match.group(1))
                hour_msgs[h] = msg

    removed, added = [], []

    for h in horas_rem:
        if h in hour_msgs:
            try:
                await hour_msgs[h].delete()
                removed.append(h)
            except discord.Forbidden:
                pass

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

    hour_msgs.reverse()

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
    description="Configura o envio automático diário do horário",
)
@app_commands.describe(
    hora_inicio="Primeira hora do horário  (ex: 14)",
    hora_fim="Última hora do horário  (ex: 23)",
    hora_post="Hora a que o bot publica a mensagem  (ex: 13)",
    cargo="Cargo a mencionar no final",
)
@app_commands.default_permissions(administrator=True)
async def slash_auto(
    interaction: discord.Interaction,
    hora_inicio: int,
    hora_fim: int,
    hora_post: int,
    cargo: discord.Role | None = None,
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
    cfg["auto_schedule"] = {
        "channel_id": interaction.channel_id,
        "hours": list(range(hora_inicio, hora_fim + 1)),
        "post_hour": hora_post,
        "role_id": cargo.id if cargo else None,
    }
    save_config(cfg)
    bot._auto_schedule = cfg["auto_schedule"]

    horas_str = " · ".join(f"{h}H" for h in range(hora_inicio, hora_fim + 1))

    embed = discord.Embed(
        title="⏰  Agendamento Automático Ativado",
        color=COLOR_GREEN,
    )
    embed.add_field(name="⏱️ Publica às", value=f"**{hora_post}H todos os dias**", inline=True)
    embed.add_field(name="📢 Canal",      value=interaction.channel.mention,        inline=True)
    if cargo:
        embed.add_field(name="📣 Cargo", value=cargo.mention, inline=True)
    embed.add_field(name="🕐 Horários",  value=horas_str, inline=False)
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
@bot.tree.command(name="status", description="Mostra o estado do agendamento automático")
@app_commands.default_permissions(manage_messages=True)
async def slash_status(interaction: discord.Interaction):
    cfg = load_config()
    sch = cfg.get("auto_schedule")

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if not sch:
        embed = discord.Embed(
            title="📊  Estado do Bot",
            description="Nenhum agendamento automático configurado.\nUsa `/auto` para criar um!",
            color=COLOR_YELLOW,
        )
    else:
        channel = bot.get_channel(sch["channel_id"])
        horas_str = " · ".join(f"{h}H" for h in sch["hours"])
        embed = discord.Embed(title="📊  Estado do Bot", color=COLOR_GREEN)
        embed.add_field(name="✅ Estado",     value="**Ativo**",                          inline=True)
        embed.add_field(name="⏱️ Publica às", value=f"**{sch['post_hour']}H**",           inline=True)
        embed.add_field(name="📢 Canal",      value=channel.mention if channel else "?",  inline=True)
        embed.add_field(name="🕐 Horários",   value=horas_str,                            inline=False)
        if sch.get("role_id"):
            role = interaction.guild.get_role(sch["role_id"])
            if role:
                embed.add_field(name="📣 Cargo", value=role.mention, inline=True)

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
        value="Posta o horário do dia.\n`hora_inicio` `hora_fim` `cargo` *(opcional)*",
        inline=False,
    )
    embed.add_field(
        name="</participacao>",
        value="Inicia uma verificação de presença de 15 minutos.\n`atividade` → nome da atividade",
        inline=False,
    )
    embed.add_field(
        name="</add>",
        value="Adiciona um membro à participação depois de fechada.\n`membro` `atividade` *(opcional)*",
        inline=False,
    )
    embed.add_field(
        name="</ranking>",
        value="Ranking de quem mais participou no mês.\n`mes` `ano` *(opcional)*",
        inline=False,
    )
    embed.add_field(
        name="</presenca>",
        value="Presenças de um membro num mês *(Gerir Mensagens)*.\n`membro` `mes` `ano` *(opcional)*",
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
        value="Configura agendamento automático diário.\n`hora_inicio` `hora_fim` `hora_post` `cargo` *(opcional)*",
        inline=False,
    )
    embed.add_field(name="</parar>",  value="Para o agendamento automático.",  inline=False)
    embed.add_field(name="</status>", value="Mostra o estado do agendamento.", inline=False)
    embed.add_field(name="</limpar>", value="Apaga mensagens do canal.",        inline=False)
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
    """Limpa comandos locais do servidor e atualiza os globais para evitar duplicações."""
    try:
        # 1. Limpa os comandos locais deste servidor
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        
        # 2. Sincroniza a árvore global
        synced = await bot.tree.sync()
        
        await ctx.send(f"✅ Comandos locais limpos! {len(synced)} comandos globais ativos. Faz Ctrl+R no teu Discord.", delete_after=10)
    except Exception as e:
        await ctx.send(f"Erro ao sincronizar: {e}", delete_after=8)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass


# ═══════════════════════════════════════════════
#  TASK — AUTO SCHEDULE
# ═══════════════════════════════════════════════
@tasks.loop(minutes=1)
async def check_auto_schedule():
    sch = getattr(bot, "_auto_schedule", None)
    if not sch:
        return

    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if now.hour == sch["post_hour"] and now.minute == 0:
        channel = bot.get_channel(sch["channel_id"])
        if channel:
            role_id = sch.get("role_id")
            role = channel.guild.get_role(role_id) if role_id else None
            # No auto, não passa atividade para usar a data do dia como título
            await post_schedule(channel, sch["hours"], role)


@tasks.loop(hours=6)
async def scheduled_config_backup():
    create_timestamped_backup(force=True)


# ═══════════════════════════════════════════════
#  EVENTOS
# ═══════════════════════════════════════════════
@bot.event
async def on_ready():
    ensure_config_available()
    create_timestamped_backup(force=True)

    cfg = load_config()
    bot._auto_schedule = cfg.get("auto_schedule", None)

    # Verifica se há alguma participação ativa pendente para retomar
    active_part = cfg.get("active_participation")
    if active_part:
        msg_id = active_part["msg_id"]
        channel_id = active_part["channel_id"]
        atividade = active_part["atividade"]
        end_time = active_part["end_time"]
        
        # Inicia a task em background
        asyncio.create_task(fechar_participacao_task(msg_id, channel_id, atividade, end_time))
        print(f"[SCH] Participacao ativa retomada para: {atividade}")

    # Sync global
    try:
        synced = await bot.tree.sync()
        print(f"[OK] {len(synced)} slash commands sincronizados globalmente")
    except Exception as e:
        print(f"[ERR] Erro ao sincronizar: {e}")

    check_auto_schedule.start()
    if not scheduled_config_backup.is_running():
        scheduled_config_backup.start()
    print(f"[OK] Bot online: {bot.user} (ID: {bot.user.id})")
    print(f"[TZ] Fuso horario: {TIMEZONE}")
    print(f"[SCH] Agendamento: {'Ativo' if bot._auto_schedule else 'Inativo'}")
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
