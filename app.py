import os
import re
import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
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
        await conn.execute("SET TIME ZONE 'America/Sao_Paulo';")
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
# Evolution API
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

    # Decide automaticamente que tipo de mensagem é
    if audio:
        payload["audio_base64"] = message
    else:
        payload["message"] = message

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



@app.post("/atualizarUserStatus") #Lovable chama isso quando: plano vence / acesso é revogado / usuário é bloqueado
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

    # [SE FOR UM ÁUDIO]
    if messageType == 'audioMessage':
        #message = await getBase64FromMediaMessage(remoteJid, messageID)
        message = 'T2dnUwACAAAAAAAAAAAAAAAAAAAAACqCBoIBE09wdXNIZWFkAQFoAIA+AAAAAABPZ2dTAAAAAAAAAAAAAAAAAAABAAAAjzLsvAEYT3B1c1RhZ3MIAAAAV2hhdHNBcHAAAAAAT2dnUwAAaJUBAAAAAAAAAAAAAgAAABWUg3QYMu/y2LTGyeC14f86sv80/wL/Lv8a/f8gS4YHCAcHBwvkwTbsxYAHyXIn4UTqUAfJecjJV8AHyXnIyVfAB8l5yMlXwAfJecjJV8BLhhQkKy0pgAK/7c2CiW9kNp1ErGBeDUZq3F2HOWY6JBfcoehLtfNaa5+necVslyV0nLHfhPfl4fmpmkp3F2CHB3MZXS9qUtzX+SDH9LdUp1xORiRNTDZiguheLqvK79svEvFaAbIT2/DYhy+x9hMggs8wG5ST91ajWAwl2kbXrMX4qTMbZ1Dr9ooE6nX0KBt+aTI1wm6Ah7OjARX3s+ua4H9zC6bTv9EmDqGrUFOCVu+KVuQGRyP6QDi4D9JssaSAqH6A4N2e8e7qVFPb7SAM8rFkTLsZ3q1xyWIBkcwvq+fS0R1k1G9prTigHVFsd0uGKCIlKS2JCkEKDP9jAGLc+QE1syLKrR/yPhT4Hy+HOCx+bgF6hiMopRKg4JLEiD1XXVN9QdwqWbTaHHyxTTGeyhNasI7YcmwMw+TwS8z68YfxdopqDqtTqGyfLou/Rr5tAPP7Eqd70agtpxrp2PD9YQWQsmCAsGpI3rQDpLqmPoLtDeYC3KhiLGqBA/MwCMVVWYhYfee/tf3AeKslcIGiOamA9CGPNEWbZyejyDKjXJps58RZ2ELS/cYRbYrywtr/AZ9XtWZ0vO7JgIqos+QH0J46RdggCnXgsgrq3mQYbf37VYv/9mOAY1v1bE5Zw1rAS4YnKiIhH4mMofT3O4doFSis//kF1pp7GsWJTbYxAdibtE0v5QFxjfuDbVI/dYi8fTWeehu/QGdERUUsAEOFs9G5VhJ2CPqu1xg5xoE2hlyL6Hmd6gsHwCso6LnhmtSKFVJmLE30bqLeIe1m1wS+OcKIij2tLHW7sVsnXPmusPBMO9mwdlC9rJbwZ+9+l61TJrC58KYwN2Qf/94kje4PW8bh2+eHOd4XCbCpLHFc7j9mBgBva21iPUMUIP56CjD+AgCg+2T/egX3OPnvZ8CL3BacrbxQKxnwS4YdGR4cHRuuORLD1+vdTH1aKnkT7vCMnMtOeclV1AiUJrR+G69gDgbgxUpjsEy+O/2hnGrBK6wd9D7JOBtimWieSgTZFbylSBBEjGP+z5+Ez1uuSTajjsKPSBiKT0hF/kDNKmctAskkbdDxSmM5bK/P2Z0WOKAYimGcm2CZSsHYilqwnz6NngYqeZnLHFPAlqjIEBg9pjKTTgZSGiyIbnwxRmFBuzmYKl5WT83rueOHe5i0S4YhIh0gHhVZBYcOSuoKQbGtyI1yOJAkGM/oIgDTzBmsTF8CxL8MgBVlWHVoVVD33HES28QqwCvwMeQuoDCj1WE2JzFz89JiqYAVZWA58PZvM9xgQ+cZM/fqDmmB1R/W8ubC4NUuwBUPPUpQhWL54+10GaQkyoR2Pl3IaRoYxEIdIp603C0oEkB0RlMnoaixg9A8FDL7+wx2kqBbDZZVRZewfqaQEkB1X9tAcdZQvP3KNCI6xUM8nQUekplCchvNqsZ2alygS4YcHBwdJRI/NVMOs77rmCf4iRyGkPDyYJeCZIKiBRiriOASQHM2TWKeXX/O1WqSxjZLlkJBHNUxsVLaUbuAEj9UEZ8H7ccPRL/+yHFbJ2mBHG1pK8jCV6xcQBI/VNBzVNFXqySNpDBNxHfoKV8Quh+v4C2w1NmmEkBfo3zYocll3pVIYI3z2rKKTmuGUbV2pKD6VRuISJygbh/G2IZdxBkey120U4kuEcYOsKg9OZIEEciDjE/KXRp/SaphxNMOUq4VGyUlfAD/S4YpIyclIYaFIKGcGxV1MX+v7iIKXYCWU4x5yLVTzT+vWJIa23uJ2l8iVT5Ceq1QgDhkDLHm+HHBhdF3dWWkwg1QKO2ejhwWvvvHxdOvZQqjXt6GrdXK/KT1aWo0n/mY01HLttEjo4chu5BOxEq6X+IjPZhtjKvw3piGqTZ4fn8oJV5zv0tleqGhHRuEXYz8wJeoRVgJd3uy8elqoqOQhn8MCNlI3GrFn5Obw9JZfAiykUz5oQA3sGhCDfkaDWmsEnZ4vn/s0G0WPpvS1aNruGWaEWfpfZtp2q0BNoKbEoBLhh0eHxgdFWMKthKw4AY1EM3GMU8lsavBX41HVdeCgBsE2kYSQHJKkEiunSBezqB5qGgjYvn/DVl8UYESYI3VMswSQG4SB4BXvnm9K0lPLdZGNyPWzxbyqKhkhMQbGWrAAVQT9Qs6UrCG6jmKhaK15Wb0YM2qDr5oEkB1Ty4bijTkcqCZihWNM8kNcQwXYTZDh3Zrh0ASQHIw6hy2TeKELZ9OaBlby95SfTSJW/35RtFxs0qVS4YfJCEjJxI9b8eI7YK0zSD4sSMNvXt34zzJ9TZtWO1HepU8x8CAJBl26sq/cVnj4jGzDEhLUCc7disKpndkBlnKXswfSjA9hMCIMA4uLPnI9bnmQ2yeehptrz0X8mI/nhbN6Kt/CjKkCWggps8qgXu+ULF5vBlKpkOdpLYOmu5EznONn1uVFHapL6XjgIA8XXpnUZ7lQsqqdtkom4xIOy8SmW/3lfXVldQzSU9h8IQO4ueuQIEw4A3fcEmrgUqsZPNaO9xx6XCUWHktRCz7qfsa7yV8CeAe7zc+p1bjXxlsS4YrOTU+LYMsu1Tqot8m+jq2zLbsby/H25FYnCy5BC6yot+cvym+6YCQYA5ztYkLC7upqVSEQql1RMdlUnPOPivBsEmAUePu2vHWqBOdXls0dfzbihAL2y1F5Da9QU2d6+/WoWPPs/tra8irvhSUH5anNVXu+TAyXo6VT0+VPbVLr3wL9Ed9qAIFzItuC7mmq2sAp+F0M62ENQQystLD/60AHkA/E5BJtjE7RMY7Yyl44m8LqCau4uybEZcdwi6mdm6Lsc3FH9ZqI646+zdXirmg5l3wGvl4eITQFW/wrYEZPa+yx0m5OSa1bUEOCOhyoRDsQsWGf+25k94Ev4Tqp8kvPEe/StYpSkQcsOugIXATUklbmTyML32jNy+sXlQ1HgCmC4mgkWOgbSPwZYxj+rxAMMHBlut7oEuGHh4WHB6zkn1WPfOOytNAViCyn48ThZqnDzxYzmohXq9lZcmyLAIT41cvWfiLce2oBLM9+QBGYekcd0HAfTBS7iqzoL+RN8HvGxbaO8wOG4txuNa9dPCDs6C/kTfB8VQvnGr0FEDPrje/tyG4ge8QRy+ZybOjVyCRPxXleqyWogCVszIQ5qAEVUycepiFcajULLOYCPvuEN3GDb6zJ/yU8qlipbbM8DCPfDkUgqWXgnhLhiErOzk7sa6+IpSagaFCMmaCQn0zCQPaRy4zkkmDgnzRzKdWn5bArK1yJM1yH9EGv38Wl2wsND6s/2Dihl4/3FnXn1ZIOQ67O813Coez28Q6m6sp9hhOAo1YpQC8jV3/0PIW5Dyt4ihbPIPu8TlkTJkFu4v/rZSPSgg9xlPP91gYiG6I74941iqdohhAvsLTdlMpo+UulNxOK8VbBpgKQ+c2CSsJkrmAySMg9k+v9iLEXF/uQtugBKq97Ww8w/J18cNoLslXvshpacGi88I+rxx9LtirSuS04VHE/1fcVvAfvcO/LnZZUqUIFXPXfaTEH4AjXsBWJyAE0SlTOb8hVUmrRgU0ipePZMYGxoYUQAumApE5jrCl33UTNlCUJ7BSi4g9W0kQcoOAOcyfbrFGHpYpS4YvJykrI6r6thLPTqoc1Psz1MDVcq0CCDRCbSbyhKnxCl7V3YIzr6jepuil+m2Z0vBo53z+qbONWknW4nRLLkjvMT02sXt0mi/PrZvGJ7rgFJ9vaQf+bgHNvFoSrPqwh9gWb53WHSeOnbb8U7d6wAXHxa8cpchGIHuFjMEdfLCzzXOwn5CvMEgU69Ofp8VocFxtOOsN8eksKhkWq4uAg622PGdy4LbkWGob3p7eOODArlRk5hYKAMShjxEB0WwS6pfhDWumtinxYnXXk5b+r9+XA3Wqqoll347brnGKvo13gHbC2rySbnAQ8xu9USOvKwMkUNfWlJWXWCh26vEjkFBLhi86My4rqGHydoPfnHK+fOs24FWZurx1wMMmXIjr0YzmdVEHqYBWMBilxUVNmFlsJq5q9kCrE213a4Ucqmd0z0uqOfy6kuel564a9Vc2hI7XzTFvTV7Juc46H/AbEpmNtHbcGOefg73+gKja2jO2vqKCo+ygqCIPFg6Tzw9DggQvNpCK1ECZg9y4fe1JRRF01JaUTttvSYfHFad37OT/wyo0gr8dRkjQAEyfM8UebjjjsOjY5jLGXrBzNXnCht6dE9iDvBWSQjBY/A//xUZDgIHEDVGD0/FYGMFI/UNwqy8LDEq/K6Ws/ih6FS6dCxOSyOiadT0BbqPMXpCMKJGtToDAghJEWqV3Lz79Z1LK+2D+iSbLbBk8hILVvR5pnTY3ERjqnH6aQbSG1jLAS4YzMCsuLY7diA5E0Q8pl1E7WEB7+d64boxW12GMD8GDFM/tZ4RNnPjdlYj31gnE/k121I0R9c0vFJEPKA71Tmy3JZQIY1JTbCuwKEXD/kpnijjlWl0MjQCzYo74jfdqtdBBN5l5dPqgxJCn0e/EPzYwoi0magKOYUPam+ne2qfze89O+MW8xhWeZPp8zzT6s/gDHMCmXPqWx4/UVI4qiAA6woZcfzTEBmqWXhFq3Rz5eAhBalNWQfDGtTcqoc8uyIHgo+uHFQ3Cy8nqgXhVcezbBMYVGA3aNuH/FaYvh6tHESH7PXwISt1BKQJR/ytApShWffCONAJ0d/PhOtgvd7mvjnxqI5lWA1j6oZodBf0ReX1E7jwaSWBLhicpIiQvppTAvet4mes/Tl3jmybtWRmGvxIy57/stQYgbUx6LObpQcY/VVi0qGiUiOgPpGGo3dp9kUddmar670H+4QSW9jz3XGSEq1I6i4Y21MHJ2lqrgx5tBynELScDABagJS4WTtef8jUr7fpZsXY/or2ZbzqcrNYXNbmPy5f0p72NA9eBaMSKw7vefoXn3jUlvcsMP0bHidewrFkAm6L5tboeCJK4JUdTiumac8go0ZlAQSyHH18i1oA4VNRV29moSxkDoRSxN9ijT+xFnKR1lCVD+zzZJvrtZqJ8mbAbPuwbqMIKLzHtsSs24I1erRqRCRloVjMYowtcS4Y1MDIxLJ/Zpp80YAXQxqYHSH9VdIcICVz64Iz35c2liUcajgpPthmC2c869DsxatnZ3lhda09YBggJnV//WrRrO7ndkROQs/pBP9EJuSMxI7nb5nzuVoqpSXLQ2IDfgC/svIJedTQ1RYYgnec+MwuiZbEmAO/fQD7LYNdoBjeLn9v/NcWrYemstTy53ML7QkY+CIOWLjCZ9wm4ROavuPGmX0CEGX5alF5NjDt7M+Zn+xZM5u+Q3IgsQR2A05qTCpBejXDfq4lFt1V6HWX0s+IxpJBi4gPzxL0vS7a9sDmYrtE2idG37EmfrXJK8dWvqIeRxCSDDgNRwq6159uMlk2DSVXvtEiac5SvyIRugxf6KJ8oyrglgGNrAT1Ct0BPZ2dTAADo5gIAAAAAAAAAAAADAAAASLROtRz/Ov8n/xH1/xj/Ef8V/v8X/zb/Jf8f/xL/Bf8oS4Y1QDgqLLTkN1F3UqA2ujU2f0dFx1JT9K0liomnYYmQQZMXiI4aICRS9xcInReacQA4U2cSLQyD/KYSqdL3RUwpS0Jl02ZhkGTpLk+g1QpqDXoTxRDsk00EyakupVUvw/zp3iMHUK6pkUn0WKmeYW1AMqdaqcGoZxujG77BEvfYihickSA4qiKGdISQhVQQ0XZce/OjOvSwSZXk7wQqYXRPgyCkvQb9LECzoB8bHmwaOO0VvleIG8bV6TdfpbCLz/0eKAfz1RTs6+mmRzSS68AF3Jr+YKitQrh13B+AjIXfGYXJu4/l4OIoVd8fixiEpGmV1eAI5nONKYWv1/xMVdbtLHyjHVO34+CMqQTbtD4zzF/oVhqcHAxxD8c9gsN8eGdrlOKfBcncEqJXpigmHN6o84weknu+tkuGMDswLiyCPFB6YJMvyraE8dwrJ158yuyauGAHQbBGn6ZLln058W3G/VhgH0vh6IHNo0Wpy9SmO1pqdMWimi4TAppwj+3haqzwxsV4RhliJOugKyWvdAwpyfp/PDRPgSJoV3s9o7VFnuzHXqATa+nJQKV6cspB8t/9yGtqCeiAWiz1FKX3aSCoRDItn6mHHvFFKc9sUG1Xxdc8uS2of6t/CK3vJl4tKLbCDKjkrHRp/NAbYBeEyhF0KfvcAqNSwkJqAJJx1W5WTvta3Z3LSrCDIlnAFrI2jEEgnjiBrMuafPtUstPqMUgoWSJ1oHfPYraF5Z+cDZjtMTdyBozdmsG2nU+YKgQ79YlL+fcqHWkhDqVACU4ojX0yNOp5YWI1iOLiYvTn2EuGMS8rMSeL7j9pYbJxrNwYAykb4WSkBQY+lF34mQTKjTahayvKHgWfbzq9GpeWe/r31Yfx7WKAjCJ/lVsG2JXsobiiBn8HWE0TYZO2wYv1XEkMeoYI1PENRAMXhkVUnaEtHb9HPECOR4pteO0Vc5LDxE6v8mkOCVX+XuZtCNnGhVWHppzXiVnsIaTzlS/qyokwga6eGKe/xUng/KADfmJK3nl5W+wmRK9lELmDGQJLZb9Pjt248Vm1dvnlfOTX4O1CwJ2APeZHZPw83fhKBmJjnAGc7XytyKTmoyyvbAein0Duz8PJfIMY+J7hY6C8UIB8qPkLZ0fKhbRjzq2tPT3Bl+nGU+k/RSi210zyVFiAS4YkHDQrJ6ABZQTr5ypthm3VOLA7bLoIukrJV2+RkzlFT1r2q48od2fBMKFfKrCxXcp4Rv9dCnSToUJeBhZZKL2CRn4HajKtQ07f7kNcjb2DyUEUh/KbHOqPYsgG81sKykP1LiezESLjNPc+aMfVgx7py/VI2GPc126AtEgRVrdxmiypz/GUamVkMJ3hRr9/1LqywwKejVprdfdXAPWG28y6OEcp3LBfp7iCulnWUD5OOzS+8Nxr7F+N2BU8BfTkswmaq3gwpY3aLRwMgK9Nay2tn8MCN+c2YgmOmxL48YwBk4R5JzKA+kNpXXnwg61ki/v1QXBLhiMoKTcytSI/nwe7XsVyidIjSAyZReb9GE0fr6mfc8HBYNkWT5pucCy068ZABH3svu0Zx5uPBl48YdzhFZmg0yHCyvClVdEilBhA2KpdruWAr8F6OX88eUhQmJobPSaOJaIpKXv9/ajK4zIg83sXnj9gKa4VrZNroMil8VgxLpkpxy01S/CStFzzb//FDGI1Vicq/rx244FWBRjb5uKpraJXlffOQL7mhw8c3ip8te6go2cIgP2C91igL6PIf00tOjSqm2rFtvV0//MISNbks0fg2kwIhtzxPIOqEcTurPP9a4ChBWQix839CfFqRkd+oDLOL2fUdJjHuyjxY3xrmDeTT7ppLL1XAN91xhjDbQ0b+0Zer9BLhi8vJCQynSs5Ppw7wL5M7ZaW+QSN9iMG9Oy1r+CshX2xeMhSBejjvLzWw7JwrdILo+HjeCCJ1bIE+TSO8czIFHZZYrzDtOyzmm5da80qZwc0KxOXtQga8q5LL2XxwoHyYNnJHARTeLC8NGMiu+TXBPYhpu7mhrEJLzORzE3tM67+W+LbpQR7NICxpdFzkh/lGTA4/VFAh1qT56n+vrdDITKfZkhY2nbLrJBgtIN9JXM9RS7QJgmqcpSfJVm13/hUg/92O4tbWY1EOQQQT9t93YK9vl4UivdgGi5fA5DAgiOT62kzJB1+qsyylJg0QCxB+l8n4RsXb3DqpiCLOVipvWSAHgUjY88bIQOrshgfbkuGKyYrLC2joO0oIHRMQsH7xApJfUnr+Y7ntqJte0mYH4PTY/WgCW+zYZGtmWrOkZO+or0KvV3hAh70lOFVbDdNQDWG3y9wVwXZNMNy/ZNcrlPrAfljV5uiBae1WfU9JpGPRstzbxxLbNUQcJAOMYwKZNshz+kjg1iaEh2+l2J4+goymwF490RL9FEsDO1is+sk5vdlDDs4M4TEyut9QGyFf17IdsDzeuSgdc/VPnCZoEv7UcW5rVHlNQ/nGxovkAp/EznJlTP8kqKS8VaQWRMUKDQi20aNCrBtpkClgsDSQrCQmwCdzaAQJXZeAaAyT3WrstSObaOiLiiYk/KrtsJhcYG0kWdy6Z2/BTd3UFpzLr80NEuGLCQmMS6lDIDCDD3YGffYPJPrl6eBK89KD/voyY5KLfBIGvBSjTEhVnTWMLZg+dNrMKUxmnLb5T9tUliRf7x9qzO/+ZYeZlAwpLRkJBgXsPCLLiiBgKZnebGfQbukMaXqoS7k2vs42xXTZ4iLB3IYK4ijf9xSNbdlNf4epd9YAKKpQjRd7hdfS/w/uE3wKnS1HbHpRj+G4zlg4f9QVWcCm1gJhB09KT7zWp96/oEeSG8w4ZucdlaAQ48Rot667xnz94UT572YVHGljzhm4Wv6sa9vIwvB+zs5s/wD5G/UhdI//1riDAEUXvMQS07t29hyQFVOs8mujZlnLsw4S4YjJTAwMB7rz65SLkBuBZOsaXYypM8lPHjkdhydJRod/XUJF1aflbRAHutkY0N32vKGyHVR0vAZxOeRbFzt8CbJ42Nod3owA1rfz5ldQJj246ZZrWBTey7TaBGSf7di+zZETJAfMMIJyvoxbmhb5QntGPL6Gm+WDS6X0ntb4KWZZbtNTnzpW8iZnZB9+/rEzzW49uK7Lw07R3HU8AYPIc4N922ZKHljwYfLRMBxRK+g8aYeHyqhUEjOqcMgcJILXBtmTj2IL2yrletqEgCsV6hC8FXj8wCKcgfJHK3hHpwz1iFC8+buea02lTuwiOJGzuG15QVx39D2CyEDJYDQl27mBDWvwYc9AnaO1MOD70NMXLDR0IBLhjcmMzY5q/SJ2C+E/4YhfMhvcQ02AM1VpcxGWhaj7VN+k1+BpANRgM6FFlyk0PjQFXUnTbjHBnC3CziYpLNssDAUN1+QhyeHfennzjU62oNNKMKcTIRI/HzXoeFhWgptDKuArFkvO201WmlHlgfkyfsNdzEz7p0Gt7g6uWFR029tGTBgmfZLnoxBDsS0ivapicU3WnEqvlS+CFQ02Bduifpe0IZ8iHOCAnFRcdG3ZWua93GRJe8NzU+GFNTb7HvOAuAqZ+nHkgAXu7bAvfKlol92uw74ZBaHizwis8el+E7DfGBxM8kSRzHPGan1hbUWDSfurqCJpo58wCm/H8eTWotDVTxAvi9zqGhXYxQQy8y49Sh+l0TwyxCHkk6AuMIPgUZ3/oUxZXZZa++hH7VwNI53TCBLhjcsIC03qkU13CUgpTE0V2Zc6fLRHK4nDrpnEayVbb0hFVCcjmSyPePfdnPMeaj2OGJyMIKwhlE6s7s2QLaaHKOiKMbd4W5VNYt1thK/pYMI6j82bk+qAaP7w/xmq6B+UBr00ymTQ99AtNDQH2uZxOMJ0xLmsjwGBmFSb6h4qkW7LHag8tGuBICzYH2Oh4TqZGJbeELXrtu9lEZtUjoC6q/MWc2dN3jY63+epALuTEWw5Ic1bmCo9noowIS7C/kAs07KSXglp7YflCkfKz7nUh280VMYRYWYYHyLCuKm+kHIyVFIqFJigB63QElMo8wDxSzGragrtjUjlQGZoZ3PQi64KEfF2GAc4rH8poUGJwQqa3NHsG9MMBiHpROzjwHXYF5KS4YxNiYzKqOYorFYB8Fa4qxMx3S0Kk5+pN+x1ovDb00gX6zhvdbe1s7a10M+8PwebZn54GKbad2iBw5txr8aJt5KpLWZAbaAAzhb0qfAXCuuIr/lG0c83M/Y4hhxBUxk6KAFICgAw/qRXEk2bt6CCPlRnJSnf3eJKF9wm84XWdtmN9WcNY6YfQfT7JBtcdr2vIEsWIOQHh+gWNoN+HLgtPDOYcC63UAaPKs+WbDWuj9F9tFwc9xKxdG2Tzx1PxuSzTg4ewovKZMU36zwMMtPRtWp8U4nl+eeeProI4QbPagNrb+81WK7fCf7LTRGpIfVgIOjIjnmtSs9BpZAqfXDMzuGVz/yDYvIQab6Li6fFJ3firXe1L6uPrum5fiugEuGKjIoMCuNf1RcvJEtY4D0/cpar0hTp1H8GDnAyLsF7VJmk04QC1fJvSf/xMIyn9yChmChHThHUX/weQAGeYeSdEqWPO9jXF2oGd8jhJhSYQQhuoj79fX9YUxt3yedCoO0WINdV3NJrf931owpocy7ZPkFAp2qrJr8C68secDg6zGMfTIcjZKjG4CtmcDO1E+yWTs/2ZIzIQmdZSQomtNEg+wq2WOiUqrxdJzR8x9RdzQfvRmCNmblJ5C2JpjYAFWKluNKS3FQxPBwg5ZGKy1iJWiSJqeNur40ltZXfqL8zzG5ibcwt5APJkarvUBDYuZfeZodKPaWUi+w6VxS+8VSkCDB3xgMz5z6WP1vxXVVCEuGIy8yLCa3lM0cDnIgck8g9jhnLyEJSVPBctlqAH7Vpc9UGOrNSmwc1rFcN7uRKf4cSI4uFjEXvCx/9JmyJ78cTd9wadAeuAC43L77axkC1O4OWg3WDXOwg0cMTCwDs3yS+3hL34HzT/KvGB6wHVNlmBdQBEUM4pwK3n1SNwwCorONvl0OKFk0h0CLw9/zEGuPavux9VDifv+3orHDulyhkmzFqjq43UEek7x+JSuK5VxQfWVrUIJaVTLLwJBWvJNWYxergLZdAznUAqSg/2CLfcU5tChAMTa9vwnQgT/Y+gIvVLw7TnGNonPu0Qck0oLFgYpEuCaqBqRX2FZxc1ImWBmDS4Y1MDEwKoIAIQ4dqTMA8KzUFEtZNF08G6Td71zkzoEe4USvRAXSs0PiFu3+6oM2hOLjKvmmnf0Ers6ogd45fQllc2V9Ixf3fEq+vS+rBfWJHg+1wQoIHhkC2aVfyxpZR7TcOYxvC8Ih9Vy0ixMSRueJFstnlDsKyXkZ6A1XFKcEfRRIunhcI93yyLMKQTm67MNd0ylZg4aLXZwDc44f/HMzfIYipkEA0vWz5jR2lyRovY/L8G7nKjvXZmP5+PxQVxxPXGrpJLN+1cfzyo3xU+EUeHqBCZq7sMSJ3cK6crntIS8DA8T/a7CbEaoJy4cNJ2RSbP70IIyIuAOpwyBAbqlw2wcMIgXVYRTuEhJj3T99WS3ZmsH+jSfZ4GEcp8k7DHi0OAkLpE9nZ1MAAKhiAwAAAAAAAAAAAAQAAADBdyTxB/8R7+/d+H1LhisuMywqjZVDxNCzSMCy29vJH8kfsEPBaR4Z78jwOrvRF9HNgX4YGC8M/WMSyi9b8Y2W/paHGN3jM5gPzO1eg9yfguOOujqAabqbxJMXO3mxdtxj0rYoVktWsz6g5xKNlUPGgPGzC7GabfPRuJvybSYOuJey9MNRFlpYjV1TDJD2xxuab3ahMDDjl9GALygpcbCNjsCCNOzuSWRVdqgtVc7f/ZkBbk52LarxiFuWViXJe3NrCzfF9UPbMNInaI1kjKRJaWu6bZr1nq/0nJax4dLN172SkyOXzZ5h+D5aFrQshr80LIKvsIvDmKpwC7EOnTkXvNsHqJ9Xd3xPOvfMpcZarL2ad+qAEd9y3/ShwEuGMSolHCaKpkNI20N7xFBs91BYodpMKFZW/6sYP6qAyD0f157p9OOhKxYpPHh7mUGvxbrUU6dAiDnXF3AXmrB/C1Ecy8wfwDATL2LTCSHgcJJ0UcyLgxRPfKTjhKVxeYvQIN1cbxTXPiGA4UTxu9jbgv1eA+v/e9AHdxMP3ColOIo1Yq1XVBeSbaYwMWV2w8snC2dNseRF/RsuWcezoA2vHuAVmdh4/NhB8oRfGallzEJKH28zhmptzgxas9KA7WK2O5HQ/MIbahkLtzHrE785y9GW0h2qJ/CaCiCeWes14XQoMSSEmLsCGxv3kQ2oS4YmJCQwKgMoIDh/Tb5DBvidyg7E50g1/HZxFdalD5vJ4k4SRRaTWcct6C2QJPaYpu5eFfJe1gNhdKB+H+5RC4/L/j1xLtxitQ9FgAPQ7uqAJP0eOYKyg3bbibAcVx1hjfc8v+aKOY1dIYMtBk0RXn3yKn2Yh0n7rFSrRxyAxvYHkdn78rshzioy/kKd+z952aZ8HDXr1v/W9woQwlrJugLonUCYhzxGssZ2Iax5NXBegnH+5gTnHYrQyQIpKC+Rs5QhXdIRxoOLC+hlevzcAq7F3XEG2bGNQrmR4eczB08cFPeoJyftO2DzI1DDpIBLhiMlKiQbF5JLWDL2FaJryAu7IwhxxR4L2yVHAwcVNmLr8GLiLQssk4AVZZZ+7k33lb/5QPJEPmdolBiUD+dOEi5UHeWkWEsnQMdDhsvWFZ+QCWjlwvukXxLDPQnVIMMKSPydmHdagNt1e+LdkRtIulvWzM8hCr7wGIj6SEgvS0YFVgway7pJHMKOzjTFk1Di0ydnn1DphTpB9CXgFWVleSnAfOkR9ioaoqoUQxwD40GhxGWLvSHYFN5XM19RBLCroW3E4ec3QpW0OOR2SgJZxKAQLpDnopVBRHCPYEuGICgoLS0SuS/OHE216caBFEkl0zkIxIznkQZToAo2ggYuEh482AHLNZtkjMLagVPvu3bpuX1lIm5jeE0eEbPFuNW7UsMbBJvN9TL3/gmGr4Z8ZLU5txyT5z+NAr6xVsjIXWlG7snViBbMsi1wiedf7c9y8V8IInrLI64nvOKhwSMGEWF4ayR3qXpmj680/EakWMpp9fz0iNc+50HpzQKK2+xQKEu9dstD0Ve+BAn4Qz7tJ5AgAvJxK39K/IPzkDDWpQqObH/qTGDFmkTB8goQKYl4MMXNxdlRDXxTy2jgxheiED7+WO0iGR2NBhs8kcDXzRiVSM+QS4MuJim1h4WrrhHzUgTVPMJzLq+nafAhdYH85yZe5oYvzmIzNlT9bLERTnHisf5ShMAniYDpjnyaSvs9CKkL7lqBfz4ezuzqy6Xfr4oRZyhBcv3z9uD0OCQpRABbQFqOsxV8yCjTgz2Hy3xaUi+s3xbeXBa6ZqiXreXhlVg='
        print(f"{phone_number} - {messageType} - Mensagem: {message}")
        if not message:
            await send_message(remoteJid, "Desculpe, houve um erro interno e não consegui ouvir seu áudio.\nTente novamente por favor.")
            return await status_ok()

        # Verifica na database localhost se número existe e qual seu status
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
                    audio=True
                )
                return await status_ok()

            else:
                await send_message(remoteJid, "⚠️ Sua conta não está ativa.\n\nRegularize no app:\nhttps://road-cost-tracker.lovable.app/")
                return await status_ok()


    # [SE FOR UM TEXTO]
    if messageType == 'conversation':
        message = data['data']['message'].get('conversation', '')
        print(f"{phone_number} - {messageType} - Mensagem: {message}")

        # Verifica na database localhost se número existe e qual seu status
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

            # Caso esteja tudo certo na validação, irá cadastrar na database localhost
            await upsert_whatsapp_user(
                phone=phone_number,
                cpf=dados_para_verificacao["cpf"]
            )

            # Feedback inicial
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
