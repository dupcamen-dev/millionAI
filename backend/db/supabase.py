import json
import time
from datetime import datetime, timezone
from supabase import create_client, Client

class SupabaseDB:
    def __init__(self, supabase_url: str, service_role_key: str):
        self.db: Client = create_client(supabase_url, service_role_key)

    def get_user_by_access_code(self, code: str) -> dict:
        resp = self.db.table("users").select("*").eq("access_code", code).execute()
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
        return None

    def get_api_keys(self, user_id: str) -> dict:
        resp = self.db.table("api_keys").select("*").eq("user_id", user_id).execute()
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
        return None

    def upsert_api_keys(self, user_id: str, api_key: str, api_secret: str, telegram_token: str = "", telegram_chat_id: str = ""):
        data = {"user_id": user_id, "api_key": api_key, "api_secret": api_secret,
                "telegram_bot_token": telegram_token, "telegram_chat_id": telegram_chat_id}
        self.db.table("api_keys").upsert(data, on_conflict="user_id").execute()

    def write_trade(self, user_id: str, symbol: str, side: str, entry_price: float,
                    quantity: float, leverage: int = 1, exit_price: float = None,
                    pnl: float = None, pnl_pct: float = None, close_reason: str = None):
        data = {
            "user_id": user_id, "symbol": symbol, "side": side,
            "entry_price": entry_price, "quantity": quantity, "leverage": leverage,
            "exit_price": exit_price, "pnl": pnl, "pnl_pct": pnl_pct,
            "close_reason": close_reason,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("trades").insert(data).execute()

    def write_equity(self, user_id: str, equity: float, balance: float, symbol: str = ""):
        data = {
            "user_id": user_id, "equity": equity, "balance": balance,
            "symbol": symbol or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("equity_curve").insert(data).execute()

    def write_log(self, user_id: str, level: str, message: str):
        data = {
            "user_id": user_id, "level": level,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("logs").insert(data).execute()

    def delete_logs(self, user_id: str):
        self.db.table("logs").delete().eq("user_id", user_id).execute()
