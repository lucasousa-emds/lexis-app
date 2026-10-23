FROM python:3.11-slim

WORKDIR /app

# Instala dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código e bases de dados
COPY . .

# Porta padrão de execução
ENV PORT=5050
EXPOSE 5050

CMD ["python", "vocab_review_server.py"]
