"""FastAPI server — REST API for Million Terminal frontend."""
import json
import os
import sys
import time
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Million Terminal API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Helpers ───────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ACCESS_CODE = os.getenv("ACCESS_CODE", "1231")
CONFIG_PATH = os.getenv("CONFIG_FILE", "") or os.path.join(os.path.dirname(__file__), "..", "best_config.json")

_db = None

def get_db():
    global _db
    if _db is None and SUPABASE_URL and SUPABASE_KEY:
        from db.supabase import SupabaseDB
        _db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)
    return _db

def verify_access(code: str):
    if not code:
        raise HTTPException(401, "Missing access code")
    db = get_db()
    if db:
        user = db.get_user_by_access_code(code)
        if not user:
            raise HTTPException(403, "Invalid access code")
        return user["id"]
    if code != ACCESS_CODE:
        raise HTTPException(403, "Invalid access code")
    return None

# ── Models ────────────────────────────────────────────────────────────
class ApiKeysPayload(BaseModel):
    api_key: str
    api_secret: str
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

class StrategyPayload(BaseModel):
    neurons: list

# ── Auth ──────────────────────────────────────────────────────────────
@app.post("/api/v1/auth/verify")
def auth_verify(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    return {"valid": True, "user_id": user_id}

# ── Balance / Positions ───────────────────────────────────────────────
@app.get("/api/v1/balance")
def get_balance(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"equity": 10.0, "balance": 10.0, "positions": []}
    equity_data = db.db.table("equity_curve").select("*").eq("user_id", user_id).order("timestamp", desc=True).limit(1).execute()
    equity = equity_data.data[0]["equity"] if equity_data.data else 0.0
    balance = equity_data.data[0]["balance"] if equity_data.data else 0.0
    trades_data = db.db.table("trades").select("*").eq("user_id", user_id).filter("closed_at", "is", "null").execute()
    positions = trades_data.data if trades_data.data else []
    return {"equity": equity, "balance": balance, "positions": positions}

# ── Logs ──────────────────────────────────────────────────────────────
@app.get("/api/v1/logs")
def get_logs(level: str = "", search: str = "", limit: int = 100, offset: int = 0, x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"logs": [], "total": 0}
    query = db.db.table("logs").select("*", count="exact").eq("user_id", user_id)
    if level:
        query = query.eq("level", level.lower())
    if search:
        query = query.ilike("message", f"%{search}%")
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return {"logs": result.data, "total": result.count}

# ── Assets / Screener ─────────────────────────────────────────────────
@app.get("/api/v1/assets/screener")
def assets_screener(x_access_code: str = Header("")):
    verify_access(x_access_code)
    from exchange.binance_rest import BinanceFuturesAPI
    from exchange.screener import AssetScreener
    api_key = os.getenv("API_KEY", "")
    api_secret = os.getenv("API_SECRET", "")
    if not api_key:
        return {"assets": []}
    api = BinanceFuturesAPI(api_key, api_secret)
    screener = AssetScreener(api)
    candidates = screener.scan(top_n=8)
    return {"assets": candidates}

# ── Strategy ──────────────────────────────────────────────────────────
@app.get("/api/v1/strategy")
def get_strategy(x_access_code: str = Header("")):
    verify_access(x_access_code)
    config_path = CONFIG_PATH
    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
        return data
    return {"neurons": [], "symbol": "", "leverage": 1}

@app.post("/api/v1/strategy")
def save_strategy(payload: StrategyPayload, x_access_code: str = Header("")):
    verify_access(x_access_code)
    config_path = CONFIG_PATH
    existing = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            existing = json.load(f)
    existing["neurons"] = [n if isinstance(n, list) else n.get("nucleus", []) for n in payload.neurons]
    with open(config_path, "w") as f:
        json.dump(existing, f)
    return {"saved": True}

# ── Settings ──────────────────────────────────────────────────────────
@app.get("/api/v1/settings/keys")
def get_settings_keys(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"api_key": "", "api_secret": "", "telegram_bot_token": "", "telegram_chat_id": ""}
    keys = db.get_api_keys(user_id)
    return {
        "api_key": keys.get("api_key", "") if keys else "",
        "api_secret": keys.get("api_secret", "") if keys else "",
        "telegram_bot_token": keys.get("telegram_bot_token", "") if keys else "",
        "telegram_chat_id": keys.get("telegram_chat_id", "") if keys else "",
    }

@app.post("/api/v1/settings/keys")
def save_settings_keys(payload: ApiKeysPayload, x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        raise HTTPException(500, "Supabase not configured")
    db.upsert_api_keys(
        user_id=user_id,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        telegram_token=payload.telegram_bot_token,
        telegram_chat_id=payload.telegram_chat_id,
    )
    return {"saved": True}

# ── Health ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}

# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=os.getenv("DEV", "0") == "1")
