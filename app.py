from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
def home():
    return {
        "status": "ok",
        "mensagem": "Projeto Python rodando no EasyPanel 🚀",
        "ambiente": os.getenv("ENV", "local")
    }

@app.get("/health")
def health():
    return {"health": "ok"}
