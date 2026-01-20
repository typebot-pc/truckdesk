from fastapi import FastAPI
import os

app = FastAPI()

PORT = int(os.environ.get("PORT", 5000))

@app.get("/")
def root():
    return "OK"

@app.get("/health")
def health():
    return {"status": "ok"}
