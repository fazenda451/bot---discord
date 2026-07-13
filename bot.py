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
    description="Inicia uma verificação de participação para uma atividade de 15 minutos",
)
@app_commands.describe(
    atividade="Nome da atividade (ex: Treino, Reunião)",
)
@app_commands.default_permissions(manage_messages=True)
async def slash_participacao(
    interaction: discord.Interaction,
    atividade: str,
):
    await interaction.response.defer(ephemeral=True)

    # Embed Inicial de Participação Aberta
    embed = discord.Embed(
        title=f"📝 Participação: {atividade.upper()}",
        description="Reage com ✅ para confirmares a tua presença nesta atividade!\n\n⏳ **Tempo restante:** 15 minutos",
        color=COLOR_BLUE,
    )
    embed.set_footer(text="A participação fecha automaticamente em 15 minutos.")
    
    # Envia a mensagem no canal público
    channel = interaction.channel
    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")

    # Confirmação efêmera para quem iniciou o comando
    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Participação para **{atividade}** iniciada no canal!",
            color=COLOR_GREEN,
        ),
        ephemeral=True,
    )

    # Função em segundo plano para contar os 15 minutos
    async def fechar_participacao_apos_tempo():
        await asyncio.sleep(900)  # 15 minutos em segundos (15 * 60)
        
        try:
            # Puxa a mensagem atualizada para ler as reações
            updated_msg = await channel.fetch_message(msg.id)
            
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
                description=f"A janela de participação para esta atividade terminou.",
                color=COLOR_RED,
            )
            embed_fechado.set_footer(text="Participação encerrada.")
            await updated_msg.edit(embed=embed_fechado)
            
            # Tenta limpar as reações para ninguém mais poder clicar
            try:
                await updated_msg.clear_reactions()
            except discord.Forbidden:
                pass
            
            # Cria a mensagem final de resumo (não-apagável)
            if users:
                nomes = ", ".join(f"{u.mention}" for u in users)
                mensagem_resumo = f"📋 **Resumo da Atividade ({atividade}):**\nOs seguintes membros participaram:\n{nomes}"
            else:
                mensagem_resumo = f"📋 **Resumo da Atividade ({atividade}):**\nNinguém confirmou a presença a tempo."
                
            await channel.send(mensagem_resumo)
            
        except discord.NotFound:
            # Se a mensagem foi excluída antes do fim do tempo
            print(f"Mensagem de participação {msg.id} não foi encontrada para encerramento.")
            
    # Executa a tarefa de contagem em segundo plano sem bloquear o bot
    asyncio.create_task(fechar_participacao_apos_tempo())


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


# ═══════════════════════════════════════════════
#  EVENTOS
# ═══════════════════════════════════════════════
@bot.event
async def on_ready():
    cfg = load_config()
    bot._auto_schedule = cfg.get("auto_schedule", None)

    # Sync global
    try:
        synced = await bot.tree.sync()
        print(f"[OK] {len(synced)} slash commands sincronizados globalmente")
    except Exception as e:
        print(f"[ERR] Erro ao sincronizar: {e}")

    check_auto_schedule.start()
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
