from fastapi import FastAPI
import os
import uvicorn
import httpx
from fastapi import FastAPI, Request


#app = FastAPI()


# Evolution
baseUrl = 'https://evolution.monitoramento.qzz.io'
apikey = 'F9AB68BD21E5-4B2B-BFEA-0AE010D4E894'
instance = 'chatbot'
remoteJid = '554198498763@s.whatsapp.net'
texto = 'Testando app...'



# O yield segura a execução até que o aplicativo termine
async def lifespan(app: FastAPI):
    yield
    print('Encerrando...')



# Usar o gerenciador de contexto "lifespan" para controlar a vida útil da aplicação
app = FastAPI(lifespan=lifespan)



# =====================================
# Cliente HTTP reutilizável
# =====================================
http_client = httpx.AsyncClient(timeout=30)



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

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=body, headers=headers)

    if response.status_code not in (200, 201):
        print(f"Falha ao enviar a mensagem para {remoteJid}: {response.status_code} - {response.text}")



@app.get("/")
def root():
    return "OK"

@app.get("/health")
def health():
    return {"status": "ok"}
    
@app.get("/teste")
async def teste():
    await send_message(remoteJid, texto)
