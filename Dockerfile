FROM python:3.11-slim

# Instalar dependências de sistema necessárias
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Definir o diretório de trabalho no container
WORKDIR /app

# Copiar os requisitos e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o resto do código do bot
COPY . .

# Comando para iniciar o bot
CMD ["python", "bot.py"]
