import re
import httpx
import random
import uvicorn
import asyncpg
import pytz
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional




# Credenciais EvolutionAPI
baseUrl = 'https://evolution.monitoramento.qzz.io'
apikey = 'F9AB68BD21E5-4B2B-BFEA-0AE010D4E894'
instance = 'chatbot'
remoteJid = '554198498763@s.whatsapp.net'




# O yield segura a execução até que o aplicativo termine
async def lifespan(app: FastAPI):
    # STARTUP
    await init_db()
    print("PostgreSQL conectado")
    yield

    # SHUTDOWN
    await http_client.aclose()
    print("Encerrando...")
    if pool:
        await pool.close()
        print("PostgreSQL desconectado")




# Usa o gerenciador de contexto "lifespan" para controlar a vida útil da aplicação
app = FastAPI(lifespan=lifespan)




# =====================================
# Cliente HTTP reutilizável
# =====================================
http_client = httpx.AsyncClient(timeout=30)




# =====================================
# Função para retornar Status OK da solicitação
# =====================================
async def status_ok():
    return JSONResponse(content={"status": "OK"}, status_code=200)




# =====================================
# Database
# =====================================
DATABASE_URL = 'postgres://usuario:123456@scripts_db-truckdesk:5432/db-truckdesk?sslmode=disable&options=-c%20timezone=America/Sao_Paulo' # URL de Conexão Interna
pool: Optional[asyncpg.Pool] = None

# Função para criar as tabelas caso elas não existam
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
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_user_events (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20),
                action VARCHAR(20) NOT NULL,
                status VARCHAR(20),
                source VARCHAR(50) DEFAULT 'lovable',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)


# Função para buscar o usuário pelo número de telefone
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


# Função para inserir o usuário na database local pelo número de telefone
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


# Função para atualizar o status do usuário - usada no endpoint POST atualizarUserStatus - para sinalizar vencimento, inativo, etc
async def update_user_status(phone: str, status: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE whatsapp_users
            SET status = $2, updated_at = NOW()
            WHERE phone = $1
            """,
            phone,
            status
        )
    return result.endswith("1")


# Função para deletar o usuário/telefone da database local - usada no endpoint POST atualizarUserStatus
async def delete_user_by_phone(phone: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM whatsapp_users
            WHERE phone = $1
            """,
            phone
        )
    return result.endswith("1")


# Função para registrar os eventos de inserção/delete da database local
async def log_user_event(
    phone: str,
    action: str,
    status: Optional[str] = None,
    source: str = "lovable"
):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO whatsapp_user_events (phone, action, status, source)
            VALUES ($1, $2, $3, $4)
            """,
            phone,
            action,
            status,
            source
        )




# =====================================
# Evolution API v2
# =====================================
# Função para enviar mensagem
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


# Função para retornar o base64 da mensagem na Evolution API v2
async def getBase64FromMediaMessage(remoteJid: str, messageID: str) -> None:
    # URL e header
    url = f"{baseUrl}/chat/getBase64FromMediaMessage/{instance}"
    headers = {
        "apikey": apikey,
        "Content-Type": "application/json"
    }

    # Body
    body = {
        "message": {"key": {"id": messageID}}
    }

    # Retorna o base64
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=body, headers=headers)

    if response.status_code in (200, 201):
        import json
        data = json.loads(response.text)
        base64 = data.get("base64")
        return base64
    else:
        return False




# =====================================
# Integração com os endpoints da Lovable
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


# Função para fazer a ponte entre o Whatsapp e o assistente do App
async def chamar_assistant(cpf: str, phone: str, message: str, audio: bool = False):
    url = "https://xghkaptoxkjdypiruinm.supabase.co/functions/v1/external-assistant"
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "cpf": cpf,
        "phone": phone,
        "callback_url": "https://chatbot.monitoramento.qzz.io/enviarResposta"
    }

    # Decide automaticamente que tipo de mensagem é (áudio ou texto)
    if audio:
        payload["audio_base64"] = message
        payload["mime_type"] = "audio/wav"
    else:
        payload["message"] = message

    try:
        response = await http_client.post(url, json=payload, headers=headers)
        if response.status_code not in (200, 201):
            print("Erro ao chamar assistant:", response.text)

    except Exception as e:
        print("Erro external-assistant:", e)




# =====================================
# Funções utilitárias
# =====================================
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


# Função para extrair os dados da mensagem padrão de cadastro/login pelo Whatsapp
'''
USUARIO: 12345678901
CODIGO: 6110a417-ef59-42f3-8d36-b8b8818338b7

Para confirmar o cadastro deste número de celular, aperte para enviar essa mensagem. 
O código é único e irá expirar em 5 minutos.
'''
def verificar_mensagem_cadastro(message: str, phone_number: str):
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




# Endpoint para testar o envio das mensagens
@app.get("/teste")
async def teste():
    await send_message(remoteJid, 'Mensagem de teste')




# [DEBUG] Endpoint para ver os usuários cadastrados na API
@app.get("/whatsapp_users", response_class=HTMLResponse)
async def debug_whatsapp_users():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT phone, cpf, status, created_at FROM whatsapp_users ORDER BY created_at DESC"
        )

    html = """
    <html><body>
    <h2>WhatsApp Users</h2>
    <table border="1" cellpadding="5">
        <tr>
            <th>Phone</th><th>CPF</th><th>Status</th><th>Created</th>
        </tr>
    """

    for r in rows:
        html += f"""
        <tr>
            <td>{r['phone']}</td>
            <td>{r['cpf']}</td>
            <td>{r['status']}</td>
            <td>{r['created_at']}</td>
        </tr>
        """

    html += "</table></body></html>"
    return html



# [DEBUG] Endpoint para ver os eventos registrados
@app.get("/whatsapp_user_events", response_class=HTMLResponse)
async def debug_whatsapp_user_events():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT phone, action, status, source, created_at
            FROM whatsapp_user_events
            ORDER BY created_at DESC
            LIMIT 200
            """
        )

    html = """
    <html><body>
    <h2>WhatsApp User Events</h2>
    <table border="1" cellpadding="5">
        <tr>
            <th>Phone</th><th>Action</th><th>Status</th><th>Source</th><th>Date</th>
        </tr>
    """

    for r in rows:
        html += f"""
        <tr>
            <td>{r['phone']}</td>
            <td>{r['action']}</td>
            <td>{r['status'] or '-'}</td>
            <td>{r['source']}</td>
            <td>{r['created_at']}</td>
        </tr>
        """

    html += "</table></body></html>"
    return html




# Endpoint para atualizar os usuários na API
# Lovable chama isso quando: plano vence / acesso é revogado / usuário é bloqueado
# TODO = Ver com a Lovable quais são os status possíveis para deixar registrado aqui
@app.post("/atualizarUserStatus")
async def lovable_user_status(payload: dict):
    phone = payload.get("phone")
    action = payload.get("action")

    # Se payload veio errado
    if not phone or not action:
        await log_user_event(phone, "error")
        raise HTTPException(400, "phone e action são obrigatórios")

    # Se pedido para atualizar
    if action == "update":
        status = payload.get("status")
        if not status:
            await log_user_event(phone, "error")
            raise HTTPException(400, "status é obrigatório para update")

        updated = await update_user_status(phone, status)

        if not updated:
            await log_user_event(phone, "update_failed", status)
            raise HTTPException(404, "usuário não encontrado")

        await log_user_event(phone, "update", status)
        return {"ok": True}

    # Se pedido para deletar
    elif action == "delete":
        deleted = await delete_user_by_phone(phone)

        if not deleted:
            await log_user_event(phone, "delete_failed")
            raise HTTPException(404, "usuário não encontrado")

        await log_user_event(phone, "delete")
        return {"ok": True}

    # Se pedido solicitou uma "action" invalida
    else:
        await log_user_event(phone, "error")
        raise HTTPException(400, "action inválida")




# Endpoint do "callback_url" para a Lovable enviar a resposta do assistente
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




# Rota do webhook das mensagens recebidas
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if not data or 'data' not in data or 'key' not in data['data'] or 'remoteJid' not in data['data']['key'] or 'message' not in data['data']:
        print(f'ERRO WEBHOOK INVÁLIDO')
        return await status_ok()

    # Variáveis
    remoteJid = data['data']['key']['remoteJid']
    phone_number = remoteJid.split('@')[0]
    messageType = data['data']['messageType']
    messageID = data['data']['key']['id']
    nome_usuario = data['data']['pushName']
    is_audio = False


    # RETORNA SE FOR UM GRUPO
    if "@g.us" in remoteJid:
        return await status_ok()

    # [SE FOR UM TEXTO]
    if messageType == 'conversation':
        message = data['data']['message'].get('conversation', '')
        print(f"{phone_number} - {messageType} - Mensagem: {message}")

    # [SE FOR UM ÁUDIO]
    elif messageType == 'audioMessage':
        is_audio = True
        message = await getBase64FromMediaMessage(remoteJid, messageID)
        print(f"{phone_number} - {messageType} - Mensagem: {message}")
        if not message:
            await send_message(remoteJid, "Desculpe, houve um erro interno e não consegui ouvir seu áudio.\nPode enviar como texto ou gravar novamente?")
            return await status_ok()

    # [SE TIPO DE MENSAGEM NÃO LISTADA ACIMA]
    else:
        await send_message(remoteJid, "Entendo apenas áudios e textos. Por favor, tente novamente.")
        return await status_ok()


    # Verifica na database da API (localhost) se o número existe e qual seu status (ativo, vencido...)
    usuario_db = await get_user_by_phone(phone_number)
    if usuario_db:
        if usuario_db["status"] == "vencido":
            await send_message(remoteJid, "⚠️ Sua assinatura venceu.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()

        if usuario_db["status"] == "ativo":
            await chamar_assistant(
                cpf=usuario_db["cpf"],
                phone=phone_number,
                message=message,
                audio=is_audio
            )
            return await status_ok()

        else:
            await send_message(remoteJid, "⚠️ Sua conta não está ativa.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()


    # Caso não tenha o número cadastrado, verifica se a mensagem recebida é aleatória ou se é a mensagem padrão de cadastro
    resultado = verificar_mensagem_cadastro(message, phone_number)

    # Verificação anti fraude 1 - caso a pessoa altere os dados da mensagem padrão
    if isinstance(resultado, dict) and resultado.get("status") == "invalid_format":
        await send_message(remoteJid,
            "⚠️ Parece que a mensagem de confirmação foi alterada.\n\n"
            "Por favor, volte ao app e gere um novo código de verificação.\n"
            "https://road-cost-tracker.lovable.app/"
        )
        return await status_ok()

    # Se for a mensagem válida de cadastro irá consultar a database da Lovable através do endpoint para ver se usuário existe através do CPF e, se existir, capturar o token temporário
    # TODO = Fazer com que haja um bloqueio caso tenham muitas solicitações erradas para não sobrecarregar o endpoint do Lovable
    if isinstance(resultado, dict) and resultado.get("status") == "ok":
        dados_para_verificacao = resultado["dados"]
        usuario = await verificar_usuario(dados_para_verificacao)
        #usuario = {'exists': True, 'authorized': True, 'account_status': 'ativo', 'plan_type': 'trial', 'nome': 'Luis Gustavo Lopes da Silveira', 'user_id': 'ee5cc143-c2c4-4576-8b3b-341276d82535', 'message': 'Usuário autorizado'}
        #usuario = {'exists': True, 'authorized': True, 'account_status': 'ativo', 'plan_type': 'trial', 'nome': 'Luis Gustavo Lopes da Silveira', 'user_id': 'ee5cc143-c2c4-4576-8b3b-341276d82535', 'message': 'Usuário autorizado', 'token': '6110a417-ef59-42f3-8d36-b8b8818338b7'}
        #usuario["token"] = "6110a417-ef59-42f3-8d36-b8b8818338b7"

        if not usuario:
            await send_message(remoteJid, "❌ Erro ao verificar seu cadastro. Por favor, tente novamente.")
            return await status_ok()

        if not usuario.get("exists"):
            await send_message(remoteJid, "Que pena, não encontrei seu cadastro. 😕\n\nCadastre-se em:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()

        if not usuario.get("authorized"):
            await send_message(remoteJid, "⛔ Seu acesso não está autorizado.\n\nPor favor, regularize no app:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()

        if usuario.get("account_status") != "ativo":
            await send_message(remoteJid, "⚠️ Sua conta não está ativa.\n\nPor favor, regularize no app:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()

        if usuario.get("token") != dados_para_verificacao.get("codigo"):
            await send_message(remoteJid, "⚠️ Código expirado.\n\nPor favor, gere um novo token pelo app:\nhttps://road-cost-tracker.lovable.app/")
            return await status_ok()

        # Caso esteja tudo certo na validação, irá cadastrar na database da API (localhost)
        await upsert_whatsapp_user(
            phone=phone_number,
            cpf=dados_para_verificacao["cpf"]
        )

        # Feedback inicial
        await send_message(remoteJid, "✅ Número cadastrado com sucesso")
        await chamar_assistant(
            cpf=dados_para_verificacao["cpf"],
            phone=phone_number,
            message="Me dê boas vindas aqui no Whatsapp"
        )
        return await status_ok()


    # Mensagem comum (usuário ainda não cadastrado)
    periodo_do_dia = await obter_periodo_do_dia()
    await send_message(remoteJid,
        f"{periodo_do_dia}, eu sou seu assistente do Motbook! 🤖\n\n"
        "Para conversar comigo, cadastre esse número no app:\n"
        "https://road-cost-tracker.lovable.app/"
    )
    return await status_ok()




if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5000, log_level='warning')




# No webhook da Evolution colocar a URL, por exemplo:
# https://bitterbird9138.cotunnel.com/webhook
# E rodar cotunnel no CMD do windows

# Retornar a webhook correta:
# https://chatbot.monitoramento.qzz.io/webhook



# requirements.txt
# fastapi
# uvicorn
# httpx
# pytz
# asyncpg



# GITHUB:
# typebot-pc
# truckdesk
# main
# /
#
# NIXPACKS (Comando de início):
# uvicorn app:app --host 0.0.0.0 --port $PORT
#
# DOMÍNIOS:
# chatbot.monitoramento.qzz.io
# 5000
