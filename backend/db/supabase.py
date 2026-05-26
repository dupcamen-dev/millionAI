import json
import os
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

    def save_weights(self, user_id: str, symbol: str, weights: list, leverage: int = 1, risk_score: float = 0.0):
        self.save_model_state(user_id, symbol, {"weights": weights, "leverage": leverage, "risk_score": risk_score})

    def save_model_state(self, user_id: str, symbol: str, state: dict):
        """Save full model state: weights + membrane + eligibility + RSTDP."""
        data = {
            "user_id": user_id, "symbol": symbol.upper(),
            "weights": json.dumps(state.get("weights", [])),
            "leverage": state.get("leverage", 1),
            "risk_score": state.get("risk_score", 0.0),
            "membrane": json.dumps(state.get("membrane", [])),
            "eligibility": json.dumps(state.get("eligibility", [])),
            "rstpd": json.dumps(state.get("rstpd", {})),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # arch_version column may not exist yet — add gracefully
        try:
            data["arch_version"] = "v2_32n"
        except Exception:
            pass
        try:
            self.db.table("model_weights").upsert(data, on_conflict="user_id,symbol").execute()
        except Exception:
            fallback_dir = os.path.join(os.path.dirname(__file__), "..", "weights")
            os.makedirs(fallback_dir, exist_ok=True)
            path = os.path.join(fallback_dir, f"{user_id}_{symbol.upper()}.json")
            with open(path, "w") as f:
                json.dump(data, f)

    def load_model_state(self, user_id: str, symbol: str) -> dict | None:
        """Load full model state from DB. Only returns compatible architecture versions."""
        try:
            resp = self.db.table("model_weights").select("*").eq("user_id", user_id).eq("symbol", symbol.upper()).execute()
            if resp.data and len(resp.data) > 0:
                row = resp.data[0]
                # Skip incompatible architectures
                arch = row.get("arch_version", "")
                if arch and arch != "v2_32n":
                    print(f"[DB] Skipping incompatible model weights (arch={arch}) for {symbol}")
                    return None
                def _parse(field):
                    val = row.get(field)
                    if isinstance(val, str):
                        return json.loads(val)
                    return val or {}
                return {
                    "weights": _parse("weights"),
                    "leverage": row.get("leverage", 1),
                    "risk_score": row.get("risk_score", 0.0),
                    "membrane": _parse("membrane"),
                    "eligibility": _parse("eligibility"),
                    "rstpd": _parse("rstpd"),
                }
        except Exception:
            pass
        fallback_dir = os.path.join(os.path.dirname(__file__), "..", "weights")
        path = os.path.join(fallback_dir, f"{user_id}_{symbol.upper()}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None
