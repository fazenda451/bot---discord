# Bot de Horários Discord 📅

Bot para gerir horários e participações num servidor Discord, com reações automáticas para cada membro indicar disponibilidade ou presença.

---

## ✨ Funcionalidades

- Publica horários formatados com uma mensagem por hora e reações de disponibilidade
- Edita horários já publicados (adicionar ou remover horas)
- Resumo de quem reagiu em cada hora
- Verificação de presença por atividade com fecho automático
- Adicionar membros à lista depois da participação fechar
- Ranking mensal de participações e consulta de presença por membro
- Backup automático do `schedule_config.json` com restauração ao reiniciar
- Agendamento automático diário do horário
- Persistência em `schedule_config.json` (agendamento, participações ativas e fechadas)
- Retoma participações ativas se o bot reiniciar

---

## 🚀 Instalação local

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar o `.env`

```bash
copy .env.example .env
```

Edita o `.env`:

```env
DISCORD_TOKEN=o_teu_token_aqui
TIMEZONE=Europe/Lisbon
```

### 3. Criar o bot no Discord

1. Vai a [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Cria uma nova aplicação → **Bot**
3. Copia o **Token** e cola no `.env`
4. Em **Bot → Privileged Gateway Intents**, ativa:
   - ✅ Message Content Intent
5. Convida o bot com as permissões: `Send Messages`, `Add Reactions`, `Manage Messages`, `Read Message History`

### 4. Iniciar o bot

```bash
python bot.py
```

---

## ☁️ Deploy na Discloud

O ficheiro `bot-discloud.zip` contém tudo o necessário para upload:

- `bot.py`
- `requirements.txt`
- `discloud.config`
- `Procfile`
- `runtime.txt`

**Não incluir** o `.env` no zip. Configura as variáveis de ambiente (`DISCORD_TOKEN`, `TIMEZONE`) no painel da Discloud.

Para regenerar o zip após alterações:

```powershell
Compress-Archive -Path bot.py,requirements.txt,discloud.config,Procfile,runtime.txt -DestinationPath bot-discloud.zip -Force
```

---

## 💾 Backup automático

O bot guarda cópias do `schedule_config.json` para evitar perda de dados:

- **`schedule_config.latest.bak`** — atualizado em cada gravação
- **`config_backups/`** — cópias com data/hora (máx. 50), a cada 30 min ou 6 horas
- **Restauro automático** — se o config estiver vazio ou corrompido ao iniciar, restaura do backup mais recente

> O histórico de participações só começa a contar a partir desta atualização. Participações anteriores não entram no ranking.

---

| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/horario` | Posta o horário do dia com reações por hora | Gerir Mensagens |
| `/participacao` | Inicia verificação de presença (padrão: 15 min) | **Todos** |
| `/add` | Adiciona membro à participação depois de fechada | Gerir Mensagens |
| `/ranking` | Ranking de quem mais participou no mês | Todos |
| `/presenca` | Quantas vezes um membro participou num mês | Gerir Mensagens |
| `/editar` | Adiciona ou remove horas de um horário existente | Gerir Mensagens |
| `/resumo` | Mostra quem reagiu em cada hora | Gerir Mensagens |
| `/auto` | Configura envio automático diário do horário | Administrador |
| `/parar` | Para o agendamento automático | Administrador |
| `/status` | Mostra o estado do agendamento automático | Gerir Mensagens |
| `/limpar` | Apaga mensagens recentes do canal | Gerir Mensagens |
| `/ajuda` | Lista todos os comandos | Todos |

### Exemplos

```
/horario atividade:FARMAR LIXO hora_inicio:16 hora_fim:20
/participacao atividade:Raid tempo:10
/add membro:@João atividade:Raid
/ranking mes:3 ano:2026
/presenca membro:@João mes:3
/editar adicionar:21 22 remover:16
/auto hora_inicio:14 hora_fim:23 hora_post:13 cargo:@Membros
```

---

## 📝 Fluxo de participação

1. Qualquer membro usa `/participacao atividade:NomeDaAtividade`
2. O bot publica um embed com reação ✅
3. Os membros reagem para confirmar presença
4. Após o tempo definido (padrão 15 min), a participação fecha automaticamente
5. É publicado um resumo com a lista de participantes
6. Se alguém chegar tarde, usa `/add membro:@Utilizador` para atualizar a lista

---

## 🎭 Reações de horário

| Emoji | Significado |
|-------|-------------|
| ✅ | Presente |
| ❌ | Não estou |
| 🕟 | Demoro 15min máximo |

---

## 🔧 Comandos de prefixo

| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `!limpar [n]` | Apaga mensagens do canal (máx. 100) | Gerir Mensagens |
| `!sync` | Sincroniza slash commands com o Discord | Dono do bot |

Usa `!sync` depois de atualizar o bot para os novos comandos aparecerem no Discord (pode demorar alguns minutos ou exigir Ctrl+R no cliente).

---

## 📢 Exemplo de horário gerado

O bot publica um embed de cabeçalho com a atividade, seguido de uma mensagem por hora:

```
🎮  FARMAR LIXO

Reage em cada hora com a tua disponibilidade:
✅ Presente
❌ Não estou
🕟 Demoro 15min máximo

🕐  16H
🕐  17H
🕐  18H
...
```

---

## 📁 Ficheiros do projeto

| Ficheiro | Função |
|----------|--------|
| `bot.py` | Código principal do bot |
| `schedule_config.json` | Configuração persistida (criado automaticamente) |
| `schedule_config.latest.bak` | Último backup do config (restauro automático) |
| `config_backups/` | Backups com data/hora (máx. 50) |
| `discloud.config` | Configuração do deploy na Discloud |
| `.env` | Variáveis de ambiente locais (não commitar) |
