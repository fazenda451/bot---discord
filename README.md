# Bot de Horários Discord 📅

Bot para gerir horários de atividades num servidor Discord, com reações automáticas para cada participante indicar a sua disponibilidade.

---

## ✨ Funcionalidades

- Publica mensagens de horário formatadas no canal
- Adiciona reações automáticas para indicar disponibilidade
- Comando de horário manual ou agendamento automático diário
- Fuso horário configurável

---

## 🚀 Instalação

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar o `.env`

Copia o ficheiro de exemplo e preenche:

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
2. Cria uma nova aplicação → Bot
3. Copia o **Token** e cola no `.env`
4. Em **Bot → Privileged Gateway Intents**, ativa:
   - ✅ Message Content Intent
5. Convida o bot com as permissões: `Send Messages`, `Add Reactions`, `Manage Messages`

### 4. Iniciar o bot

```bash
python bot.py
```

---

## 📋 Comandos

| Comando | Descrição | Permissão |
|--------|-----------|-----------|
| `!horario <atividade> [horas...]` | Posta horário manualmente | Gerir Mensagens |
| `!horario_auto <atividade> <inicio> <fim>` | Agenda envio diário | Administrador |
| `!horario_parar` | Para o agendamento | Administrador |
| `!ajuda_horario` | Mostra ajuda | Todos |

### Exemplos

```
!horario "FARMAR LIXO" 16 17 18 19 20
!horario "RAID BOSS" 21 22 23
!horario_auto "FARMAR LIXO" 16 20
```

---

## 🎭 Reações

| Emoji | Significado |
|-------|-------------|
| ✅ | Presente |
| ❌ | Não estou |
| 🕟 | Demoro 15min máximo |
| 🅿️ | Promessa |

---

## 📢 Exemplo de mensagem gerada

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FARMAR LIXO

16H
17H
18H
19H
20H

✅ Presente  |  ❌ Não estou  |  🕟 Demoro 15min máx  |  🅿️ Promessa
```
