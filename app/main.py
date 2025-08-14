from fastapi import FastAPI
from app.api.chat_router import router as chat_router

app = FastAPI(
    title="SaaS Business Intelligence Agent API (Ollama Edition)",
    description="An API for interacting with a local agent for SaaS KPI analysis using Ollama.",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(chat_router, prefix="/agent", tags=["Agent"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the SaaS BI Agent API (Ollama). Head to /docs to interact with the agent."}