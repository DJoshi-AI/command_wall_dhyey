from fastapi import APIRouter, HTTPException, Depends
from app.schema.chat import ChatRequest, ChatResponse
from app.agent.graph import GraphWrapper

router = APIRouter()

def get_agent_graph():
    # This creates a new instance per request. For production, consider a singleton pattern.
    return GraphWrapper()

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest, agent_graph: GraphWrapper = Depends(get_agent_graph)):
    try:
        answer, updated_history = agent_graph.invoke(request.query, request.conversation_history)
        return ChatResponse(answer=answer, updated_history=updated_history)
    except Exception as e:
        print(f"An error occurred in chat_with_agent: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")

