from pyexpat.errors import messages

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class EchoRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return {"message": "Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/echo")
def echo(data: EchoRequest):
    return {
        "original_message": data.message,
        "uppercase_message": data.message.upper(),
        "length": len(data.message)
    }
