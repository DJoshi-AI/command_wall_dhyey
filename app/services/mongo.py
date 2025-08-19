#mongo.py
import os
import datetime
from typing import List, Dict, Any, Optional

from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/")
        _client = MongoClient(uri)
    return _client


def get_db() -> Database:
    global _db
    if _db is None:
        db_name = os.getenv("MONGO_DB", "my_agent_db")
        _db = get_mongo_client()[db_name]
        ensure_indexes(_db)
    return _db


def ensure_indexes(db: Database):
    db.clients.create_index([("client_id", ASCENDING)], unique=True)
    db.sessions.create_index([("session_id", ASCENDING)], unique=True)
    db.messages.create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])
    db.kpis.create_index([("client_id", ASCENDING), ("date", ASCENDING)])


def seed_dummy_data(db: Database):
    # Seed clients (4 clients)
    if db.clients.count_documents({}) == 0:
        clients = [
            {"client_id": "client1", "name": "Alice", "email": "alice@example.com"},
            {"client_id": "client2", "name": "Bob", "email": "bob@example.com"},
            {"client_id": "client3", "name": "Charlie", "email": "charlie@example.com"},
            {"client_id": "client4", "name": "Diana", "email": "diana@example.com"},
        ]
        db.clients.insert_many(clients)
        print("✅ Dummy clients inserted")
    else:
        print("⚡ Clients already exist")

    # Seed exactly 5 days of KPI data per client (so every metric has 5 points)
    if db.kpis.count_documents({}) == 0:
        kpi_docs: List[Dict[str, Any]] = []
        today = datetime.date.today()
        # Deterministic-ish values for clarity
        for c in db.clients.find({}, {"client_id": 1}):
            cid = c["client_id"]
            # Create 5 days of data
            base_mrr = 12000 if cid == "client1" else 14500 if cid == "client2" else 16000 if cid == "client3" else 18000
            churn_baseline = 0.03 if cid in {"client1", "client2"} else 0.028
            users_base = 800 if cid in {"client1", "client3"} else 900

            for i in range(5):
                day = today - datetime.timedelta(days=4 - i)  # oldest to newest
                mrr = base_mrr + i * 120 - (i % 2) * 60
                churn_rate = round(churn_baseline + (i - 2) * 0.002, 4)  # small variation across 5 points
                active_users = users_base + i * 15 - (i % 3) * 10

                kpi_docs.append(
                    {
                        "client_id": cid,
                        "date": day.isoformat(),
                        "mrr": float(round(mrr, 2)),
                        "churn_rate": float(churn_rate),
                        "active_users": int(active_users),
                    }
                )
        if kpi_docs:
            db.kpis.insert_many(kpi_docs)
        print("✅ Dummy KPI data (5 days per client) inserted")
    else:
        print("⚡ KPI data already exist")


# Sessions: store active client_id per session
def get_active_client_id(session_id: str) -> str:
    db = get_db()
    doc = db.sessions.find_one({"session_id": session_id})
    return doc.get("active_client_id", "") if doc else ""


def set_active_client_id(session_id: str, client_id: str) -> bool:
    db = get_db()
    if not db.clients.find_one({"client_id": client_id}):
        return False
    db.sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "session_id": session_id,
                "active_client_id": client_id,
                "updated_at": datetime.datetime.utcnow(),
            }
        },
        upsert=True,
    )
    return True


# Messages: persist chat history
def add_message(session_id: str, role: str, content: str):
    db = get_db()
    db.messages.insert_one(
        {
            "session_id": session_id,
            "role": role,  # "human" or "ai"
            "content": content,
            "created_at": datetime.datetime.utcnow(),
        }
    )


def get_messages(session_id: str, limit: int = 50) -> List[Dict[str, str]]:
    db = get_db()
    cursor = (
        db.messages.find({"session_id": session_id})
        .sort("created_at", ASCENDING)
        .limit(limit)
    )
    out: List[Dict[str, str]] = []
    for doc in cursor:
        out.append({"type": doc["role"], "content": doc["content"]})
    return out


# Optional helpers
def list_clients() -> List[Dict[str, Any]]:
    db = get_db()
    return list(db.clients.find({}, {"_id": 0}))


def create_client(client: Dict[str, Any]) -> bool:
    db = get_db()
    if not client.get("client_id") or db.clients.find_one({"client_id": client["client_id"]}):
        return False
    db.clients.insert_one(client)
    return True