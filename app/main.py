#main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat_router import router as chat_router
from app.agent.graph import GraphWrapper
from app.services.mongo import get_db, seed_dummy_data

app = FastAPI(title="My Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize graph once
app.state.graph = GraphWrapper(
    model_name="qwen2.5:7b-instruct",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
)

# Routes
app.include_router(chat_router)

@app.on_event("startup")
def on_startup():
    db = get_db()
    seed_dummy_data(db)
    print("✅ Mongo ready and dummy clients seeded")

@app.get("/")
def root():
    return {"status": "ok", "message": "Agent is running 🚀"}