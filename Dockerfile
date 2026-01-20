FROM python:3.11-slim

# Diretório de trabalho dentro do container
WORKDIR /app

# Copia dependências
COPY requirements.txt .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do projeto
COPY . .

# Expõe a porta (FastAPI)
EXPOSE 5000

# Comando para rodar a aplicação
CMD ["sh", "-c", "echo 'Container iniciado' && sleep infinity"]
