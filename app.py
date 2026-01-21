import os
import re
import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import pytz
from datetime import datetime
from typing import Optional
import asyncpg




# Evolution
baseUrl = 'https://evolution.monitoramento.qzz.io'
apikey = 'F9AB68BD21E5-4B2B-BFEA-0AE010D4E894'
instance = 'chatbot'
remoteJid = '554198498763@s.whatsapp.net'
texto = 'Testando app...'



lista_cadastrados = {}



# O yield segura a execução até que o aplicativo termine
async def lifespan(app: FastAPI):
    # STARTUP
    await init_db()
    print("PostgreSQL conectado")

    yield
    await http_client.aclose()
    print("Encerrando...")

    # SHUTDOWN
    if pool:
        await pool.close()
        print("PostgreSQL desconectado")



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
# DATABASE
# =====================================
#DATABASE_URL = 'postgres://usuario:123456@easypanel.monitoramento.qzz.io:6000/db-truckdesk?sslmode=disable'
DATABASE_URL = 'postgres://usuario:123456@scripts_db-truckdesk:5432/db-truckdesk?sslmode=disable'
pool: Optional[asyncpg.Pool] = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_users (
                phone VARCHAR(20) PRIMARY KEY,
                cpf VARCHAR(14) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ativo',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)

async def get_user_by_phone(phone: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT phone, cpf, status
            FROM whatsapp_users
            WHERE phone = $1
            """,
            phone
        )

async def upsert_whatsapp_user(phone: str, cpf: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO whatsapp_users (phone, cpf, status)
            VALUES ($1, $2, 'ativo')
            ON CONFLICT (phone)
            DO UPDATE SET
                cpf = EXCLUDED.cpf,
                status = 'ativo',
                updated_at = NOW()
            """,
            phone,
            cpf
        )

async def update_user_status(phone: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE whatsapp_users
            SET status = $2, updated_at = NOW()
            WHERE phone = $1
            """,
            phone,
            status
        )

async def delete_user_by_phone(phone: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM whatsapp_users
            WHERE phone = $1
            """,
            phone
        )



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
        "text": text,
        "linkPreview": False
    }

    response = await http_client.post(url, json=body, headers=headers)

    if response.status_code not in (200, 201):
        print(f"Falha ao enviar a mensagem para {remoteJid}: {response.status_code} - {response.text}")



# =====================================
# Integração
# =====================================
async def verificar_usuario(dados: dict) -> Optional[dict]:
    url = "https://xghkaptoxkjdypiruinm.supabase.co/functions/v1/verify-user"
    headers = {"Content-Type": "application/json"}
    payload = dados
    try:
        response = await http_client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            print("Erro ao verificar usuário:", response.text)
            return None
        return response.json()

    except Exception as e:
        print("Erro verify-user:", e)
        return None



async def chamar_assistant(cpf: str, phone: str, message: str):
    url = "https://xghkaptoxkjdypiruinm.supabase.co/functions/v1/external-assistant"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "cpf": cpf,
        "phone": phone,
        "message": message,
        "callback_url": "https://chatbot.monitoramento.qzz.io/enviarResposta"
    }
    try:
        response = await http_client.post(url, json=payload, headers=headers)
        if response.status_code not in (200, 201):
            print("Erro ao chamar assistant:", response.text)

    except Exception as e:
        print("Erro external-assistant:", e)



def extrair_dados(message: str, phone_number: str):
    try:
        # Se a mensagem contém as palavras-chave, mas não bate no padrão → tentativa inválida
        if "USUARIO:" in message or "CODIGO:" in message:
            padrao = re.compile(
                r"USUARIO:\s*(\d{11})\s*"
                r"CODIGO:\s*([0-9a-fA-F]{8}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12})",
                re.MULTILINE
            )

            match = padrao.search(message)
            if not match:
                return {"status": "invalid_format"}
            cpf = match.group(1)
            codigo = match.group(2)

            return {
                "status": "ok",
                "dados": {
                    "cpf": cpf,
                    "codigo": codigo,
                    "telefone": phone_number
                }
            }

        # Mensagem comum, não é tentativa de cadastro
        return None

    except Exception:
        return None



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



@app.post("/atualizarUserStatus") #Lovable chama isso quando: plano vence / acesso é revogado / usuário é bloqueado
async def lovable_user_status(payload: dict):
    phone = payload.get("phone")
    action = payload.get("action")

    if not phone or not action:
        return {"ok": False, "error": "phone e action são obrigatórios"}

    if action == "update":
        status = payload.get("status")

        if not status:
            return {"ok": False, "error": "status é obrigatório para update"}

        await update_user_status(phone, status)
        return {"ok": True, "action": "update", "status": status}

    elif action == "delete":
        await delete_user_by_phone(phone)
        return {"ok": True, "action": "delete"}

    else:
        return {"ok": False, "error": "action inválida"}



@app.post("/enviarResposta")
async def enviarResposta(request: Request):
    data = await request.json()

    cpf = data.get("cpf")
    phone = data.get("phone")
    response_text = data.get("response")

    if not phone or not response_text:
        return {"status": "invalid payload"}

    remoteJid = f"{phone}@s.whatsapp.net"

    await send_message(remoteJid, response_text)

    return {"status": "ok"}




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

        usuario_db = await get_user_by_phone(phone_number)
        if usuario_db:
            if usuario_db["status"] == "vencido":
                await send_message(remoteJid,"⚠️ Sua assinatura venceu.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()

            if usuario_db["status"] == "ativo":
                await chamar_assistant(
                    cpf=usuario_db["cpf"],
                    phone=phone_number,
                    message=message
                )
                return await status_ok()

            else:
                await send_message(remoteJid,"⚠️ Sua conta não está ativa.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()

        # Pula a etapa de verificação se o usuário já possui o número cadastrado
        # if phone_number in lista_cadastrados:
        #     await chamar_assistant(
        #         cpf=lista_cadastrados[phone_number],
        #         phone=phone_number,
        #         message=message
        #     )
        #     return await status_ok()

        # Caso não tenha o número cadastrado, verifica a mensagem recebida
        # Tenta extrair a mensagem padrão que virá pelo app
        resultado = extrair_dados(message, phone_number)

        # Caso a pessoa altere os dados da mensagem padrão (tentativa de fraude)
        if isinstance(resultado, dict) and resultado.get("status") == "invalid_format":
            await send_message(remoteJid,
                "⚠️ Parece que a mensagem de confirmação foi alterada.\n\n"
                "Por favor, volte ao app e gere um novo código de verificação.\n"
                "https://road-cost-tracker.lovable.app/"
            )
            return await status_ok()

        # Mensagem válida
        # TODO = Fazer com que haja um bloqueio caso tenham muitas solicitações erradas para não sobrecarregar o endpoint do Lovable
        if isinstance(resultado, dict) and resultado.get("status") == "ok":
            dados_para_verificacao = resultado["dados"]
            usuario = await verificar_usuario(dados_para_verificacao)
            #usuario = {'exists': True, 'authorized': True, 'account_status': 'ativo', 'plan_type': 'trial', 'nome': 'Luis Gustavo Lopes da Silveira', 'user_id': 'ee5cc143-c2c4-4576-8b3b-341276d82535', 'message': 'Usuário autorizado'}
            #usuario = {'exists': True, 'authorized': True, 'account_status': 'ativo', 'plan_type': 'trial', 'nome': 'Luis Gustavo Lopes da Silveira', 'user_id': 'ee5cc143-c2c4-4576-8b3b-341276d82535', 'message': 'Usuário autorizado', 'token': '6110a417-ef59-42f3-8d36-b8b8818338b7'}
            #usuario["token"] = "6110a417-ef59-42f3-8d36-b8b8818338b7"

            if not usuario:
                await send_message(remoteJid, "❌ Erro ao verificar seu cadastro, tente novamente.")
                return await status_ok()

            if not usuario.get("exists"):
                await send_message(remoteJid, "Que pena, não encontrei seu cadastro. 😕\n\nCadastre-se em:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()

            if not usuario.get("authorized"):
                await send_message(remoteJid, "⛔ Seu acesso não está autorizado.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()

            if usuario.get("account_status") != "ativo":
                await send_message(remoteJid, "⚠️ Sua conta não está ativa.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()

            # if usuario.get("token") != dados_para_verificacao.get("codigo"):
            #     await send_message(remoteJid, "⚠️ Código expirado.\n\nGere um novo pelo app:\nhttps://road-cost-tracker.lovable.app/")
            #     return await status_ok()

            #lista_cadastrados[phone_number] = dados_para_verificacao["cpf"]
            await upsert_whatsapp_user(
                phone=phone_number,
                cpf=dados_para_verificacao["cpf"]
            )

            await send_message(remoteJid, "✅ Número cadastrado com sucesso")
            await chamar_assistant(
                cpf=dados_para_verificacao["cpf"],
                phone=phone_number,
                message="Me dê boas vindas"
            )
            return await status_ok()


        # Mensagem comum (usuário ainda não cadastrado)
        await send_message(remoteJid,
            "Oi, eu sou seu assistente do Motbook! 🤖\n\n"
            "Para conversar comigo, cadastre esse número no app:\n"
            "https://road-cost-tracker.lovable.app/"
        )




if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5000, log_level='warning')



# No webhook da Evolution colocar a URL, por exemplo:
# https://bitterbird9138.cotunnel.com/webhook
# E rodar cotunnel no CMD do windows

# Retornar a webhook correta:
# https://chatbot.monitoramento.qzz.io/webhook
