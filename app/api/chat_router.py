#chat_router.py
from fastapi import APIRouter, HTTPException, Request
from app.schema.chat import ChatRequest, ChatResponse
from app.services.mongo import list_clients, create_client

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(req: ChatRequest, request: Request):
    graph = request.app.state.graph
    try:
        answer, updated_history = graph.invoke(
            query=req.query,
            history=req.history or [],
            client_id=req.client_id,
            session_id=req.session_id,
        )
        return ChatResponse(answer=answer, history=updated_history, client_id=req.client_id)
    except Exception as e:
        print("An error occurred in chat_with_agent:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients")
def get_clients():
    return list_clients()


@router.post("/clients")
def add_client(client: dict):
    ok = create_client(client)
    if not ok:
        raise HTTPException(status_code=400, detail="Client already exists or invalid payload")
    return {"ok": True}