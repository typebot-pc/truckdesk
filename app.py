import os
import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import pytz
from datetime import datetime



# Evolution
baseUrl = 'https://evolution.monitoramento.qzz.io'
apikey = 'F9AB68BD21E5-4B2B-BFEA-0AE010D4E894'
instance = 'chatbot'
remoteJid = '554198498763@s.whatsapp.net'
texto = 'Testando app...'



# O yield segura a execução até que o aplicativo termine
async def lifespan(app: FastAPI):
    yield
    await http_client.aclose()
    print("Encerrando...")



# Usar o gerenciador de contexto "lifespan" para controlar a vida útil da aplicação
app = FastAPI(lifespan=lifespan)



# =====================================
# Cliente HTTP reutilizável
# =====================================
http_client = httpx.AsyncClient(timeout=30)



# Função para retornar Status OK da solicitação
async def status_ok():
    return JSONResponse(content={"status": "OK"}, status_code=200)



# Função para retornar o período do dia
async def obter_periodo_do_dia():
    # Define o fuso horário de Brasília
    br_tz = pytz.timezone('America/Sao_Paulo')

    # Obtém a hora atual
    hora_atual = datetime.now(br_tz).hour

    if 5 <= hora_atual < 12:
        return "Bom dia"
    elif 12 <= hora_atual < 18:
        return "Boa tarde"
    else:
        return "Boa noite"



# =====================================
# Enviar mensagem (Evolution)
# =====================================
async def send_message(remoteJid: str, text: str) -> None:
    url = f"{baseUrl}/message/sendText/{instance}"
    headers = {
        "apikey": apikey,
        "Content-Type": "application/json"
    }
    body = {
        "number": remoteJid,
        "text": text
    }

    response = await http_client.post(url, json=body, headers=headers)

    if response.status_code not in (200, 201):
        print(f"Falha ao enviar a mensagem para {remoteJid}: {response.status_code} - {response.text}")



# =====================================
# Endpoints
# =====================================
@app.get("/")
def root():
    return "OK"



@app.get("/health")
def health():
    return {"status": "ok"}



@app.get("/teste")
async def teste():
    await send_message(remoteJid, texto)



# Rota do webhook
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if not data or 'data' not in data or 'key' not in data['data'] or 'remoteJid' not in data['data']['key'] or 'message' not in data['data']:
        print(f'ERRO WEBHOOK INVÁLIDO')
        return await status_ok()

    # Captura as variáveis
    remoteJid = data['data']['key']['remoteJid']
    phone_number = remoteJid.split('@')[0]
    messageType = data['data']['messageType']
    messageID = data['data']['key']['id']
    nome_usuario = data['data']['pushName']

    # ENCERRA SE FOR UM GRUPO
    if "@g.us" in remoteJid:
        return await status_ok()

    # [SE FOR UM TEXTO]
    if messageType == 'conversation':
        message = data['data']['message'].get('conversation', '')
        print(f"{phone_number} - {messageType} - Mensagem: {message}")

        periodo_do_dia = await obter_periodo_do_dia()
        await send_message(remoteJid, f'{periodo_do_dia}, {nome_usuario}!')
