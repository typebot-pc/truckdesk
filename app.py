from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
def root():
    return "OK"

@app.get("/health")
def health():
    return {"status": "ok"}
