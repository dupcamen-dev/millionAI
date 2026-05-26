"""FastAPI server — REST API for Million Terminal frontend — multi-user support."""
import json
import os
import queue
import sys
import time
import threading
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Million Terminal API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ACCESS_CODE = os.getenv("ACCESS_CODE", "1231")
CONFIG_PATH = os.getenv("CONFIG_FILE", "") or os.path.join(os.path.dirname(__file__), "..", "best_config.json")
MAX_TRADERS = 3

# ── State ────────────────────────────────────────────────────────────
_db = None
_start_lock = threading.Lock()
_trader_instances = {}  # {user_id: {"trader", "thread", "listener", "telegram_bot", "user_id", "initializing", "init_error"}}
_balance_caches = {}    # {user_id: {"equity", "positions", "ts"}}

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

def get_user_keys(user_id: str):
    db = get_db()
    if not db:
        return None, None
    keys = db.get_api_keys(user_id)
    if not keys:
        return None, None
    return keys.get("api_key"), keys.get("api_secret")

def _get_instance(user_id: str):
    return _trader_instances.get(user_id)

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
    now = time.time()

    inst = _get_instance(user_id)
    if inst and inst["trader"] is not None and not inst["initializing"]:
        t = inst["trader"]
        equity = round(t.equity, 2)
        positions = []
        try:
            api_key, api_secret = get_user_keys(user_id)
            if not api_key or not api_secret:
                return {"equity": equity, "balance": equity, "positions": []}
            raw_positions = t.binance.get_positions()
            for p in raw_positions:
                amt = float(p.get("positionAmt", 0))
                positions.append({
                    "symbol": p.get("symbol", ""),
                    "side": "BUY" if amt > 0 else "SELL",
                    "entry_price": float(p.get("entryPrice", 0)),
                    "quantity": abs(amt),
                    "leverage": int(float(p.get("leverage", 1))),
                    "pnl": float(p.get("unRealizedProfit", 0)),
                })
        except Exception:
            pass
        return {"equity": equity, "balance": equity, "positions": positions}

    cache = _balance_caches.get(user_id, {"equity": 0.0, "positions": [], "ts": 0.0})
    if now - cache["ts"] < 30 and cache["ts"] > 0:
        return {"equity": cache["equity"], "balance": cache["equity"], "positions": cache["positions"]}

    api_key, api_secret = get_user_keys(user_id)
    if not api_key or not api_secret:
        return {"equity": 0, "balance": 0, "positions": []}
    if api_key:
        try:
            from exchange.binance_rest import BinanceFuturesAPI, BinanceAPIError
            api = BinanceFuturesAPI(api_key, api_secret)
            bal = api.get_balance()
            equity = float(bal) if bal else 0.0
            positions = []
            try:
                raw_positions = api.get_positions()
                for p in raw_positions:
                    amt = float(p.get("positionAmt", 0))
                    positions.append({
                        "symbol": p.get("symbol", ""),
                        "side": "BUY" if amt > 0 else "SELL",
                        "entry_price": float(p.get("entryPrice", 0)),
                        "quantity": abs(amt),
                        "leverage": int(float(p.get("leverage", 1))),
                        "pnl": float(p.get("unRealizedProfit", 0)),
                    })
            except Exception:
                pass
            _balance_caches[user_id] = {"equity": equity, "positions": positions, "ts": now}
            return {"equity": equity, "balance": equity, "positions": positions}
        except Exception:
            pass

    return {"equity": cache.get("equity", 0), "balance": cache.get("equity", 0), "positions": cache.get("positions", [])}

# ── Logs ──────────────────────────────────────────────────────────────
@app.get("/api/v1/logs")
def get_logs(level: str = "", search: str = "", limit: int = 100, offset: int = 0, since_id: int = 0, x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"logs": [], "total": 0}
    query = db.db.table("logs").select("*", count="exact").eq("user_id", user_id)
    if level:
        query = query.eq("level", level.lower())
    if search:
        query = query.ilike("message", f"%{search}%")
    if since_id:
        query = query.gt("id", since_id)
    query = query.order("id", desc=False).range(offset, offset + limit - 1)
    result = query.execute()
    return {"logs": result.data, "total": result.count}

@app.delete("/api/v1/logs")
def delete_logs(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"deleted": 0}
    db.delete_logs(user_id)
    return {"deleted": True}

# ── Assets / Screener ─────────────────────────────────────────────────
@app.get("/api/v1/assets/screener")
def assets_screener(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    from exchange.binance_rest import BinanceFuturesAPI, BinanceAPIError
    from exchange.screener import AssetScreener
    api_key, api_secret = get_user_keys(user_id)
    if not api_key or not api_secret:
        return {"assets": []}
    try:
        api = BinanceFuturesAPI(api_key, api_secret)
        screener = AssetScreener(api)
        candidates = screener.scan(top_n=8)
        return {"assets": candidates}
    except BinanceAPIError as e:
        raise HTTPException(502, f"Binance API error: {e.message}")
    except Exception as e:
        raise HTTPException(500, f"Screener error: {e}")

# ── Strategy ──────────────────────────────────────────────────────────
@app.get("/api/v1/strategy")
def get_strategy(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)

    # If trader is running, return its live weights
    inst = _get_instance(user_id)
    if inst and inst["trader"] is not None and not inst["initializing"]:
        t = inst["trader"]
        if t.neurons:
            return {
                "neurons": [n.nucleus.tolist() if hasattr(n, 'nucleus') else n for n in t.neurons],
                "symbol": t.symbol,
                "leverage": t.leverage,
                "live": True,
                "trades": t.trades,
                "wins": t.wins,
            }

    # Fall back to DB saved state for the user's last symbol
    db = get_db()
    if db:
        try:
            resp = db.db.table("model_weights").select("*").eq("user_id", user_id).order("updated_at", desc=True).limit(1).execute()
            if resp.data and len(resp.data) > 0:
                row = resp.data[0]
                w = row.get("weights")
                if isinstance(w, str):
                    w = json.loads(w)
                return {
                    "neurons": w if w else [],
                    "symbol": row.get("symbol", ""),
                    "leverage": row.get("leverage", 1),
                    "live": False,
                    "risk_score": row.get("risk_score", 0),
                }
        except Exception:
            pass

    return {"neurons": [], "symbol": "", "leverage": 1, "live": False}

@app.get("/api/v1/strategy/models")
def list_saved_models(x_access_code: str = Header("")):
    """Return all saved model states for this user."""
    user_id = verify_access(x_access_code)
    db = get_db()
    if not db:
        return {"models": []}
    try:
        resp = db.db.table("model_weights").select("symbol,leverage,risk_score,updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
        if resp.data:
            return {"models": resp.data}
    except Exception:
        pass
    return {"models": []}

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

# ── Trader Control (Multi-user) ───────────────────────────────────────
@app.post("/api/v1/trader/start")
def trader_start(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)

    with _start_lock:
        if len(_trader_instances) >= MAX_TRADERS:
            raise HTTPException(429, f"Maximum {MAX_TRADERS} concurrent traders reached. Try again later.")
        if user_id in _trader_instances:
            inst = _trader_instances[user_id]
            if inst["initializing"]:
                raise HTTPException(409, "Your trader is still initializing, please wait.")
            if inst["trader"] is not None:
                raise HTTPException(409, "You already have a running trader. Stop it first.")
            del _trader_instances[user_id]

        _trader_instances[user_id] = {"trader": None, "thread": None, "listener": None, "telegram_bot": None, "user_id": user_id, "initializing": True, "init_error": None}

    api_key, api_secret = get_user_keys(user_id)
    if not api_key or not api_secret:
        _trader_instances[user_id]["initializing"] = False
        _trader_instances[user_id]["init_error"] = "No API keys configured. Set them in Settings first."
        raise HTTPException(400, "No API keys configured. Set them in Settings first.")

    db = get_db()

    def _init_trader():
        try:
            from trader.real import RealTrader
            from exchange.binance_ws import BinanceWSListener
            from exchange.binance_rest import BinanceAPIError
            from telegram.bot import TelegramBot

            msg_queue = None
            telegram_token = ""
            if db:
                keys = db.get_api_keys(user_id)
                if keys:
                    telegram_token = keys.get("telegram_bot_token", "")
                    telegram_chat_id = keys.get("telegram_chat_id", "")
            telegram_bot = None
            if telegram_token:
                msg_queue = queue.Queue()
                telegram_bot = TelegramBot(telegram_token, msg_queue, trader_ref=lambda: _trader_instances.get(user_id, {}).get("trader"))
                t = threading.Thread(target=telegram_bot.run, daemon=True)
                t.start()

            trader = RealTrader(
                api_key, api_secret,
                symbol="", leverage=1,
                config_file=CONFIG_PATH if os.path.exists(CONFIG_PATH) else None,
                db=db, telegram_queue=msg_queue,
                auto_symbol=True,
            )
            trader.user_id = user_id
            trader._init_exchange()

            listener = BinanceWSListener(trader.on_candle)
            thread = threading.Thread(target=listener.connect, args=(trader.symbol, "5m"), daemon=True)
            thread.start()

            _trader_instances[user_id] = {
                "trader": trader, "thread": thread, "listener": listener,
                "telegram_bot": telegram_bot, "user_id": user_id,
                "initializing": False, "init_error": None,
            }
        except Exception as e:
            if user_id in _trader_instances:
                _trader_instances[user_id]["initializing"] = False
                _trader_instances[user_id]["init_error"] = str(e)

    threading.Thread(target=_init_trader, daemon=True).start()

    return {"status": "starting", "message": "Initializing trader with backtest... This may take a few minutes."}

@app.post("/api/v1/trader/stop")
def trader_stop(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)

    inst = _get_instance(user_id)

    if inst is None:
        raise HTTPException(409, "No trader running.")

    if inst["initializing"]:
        _trader_instances.pop(user_id, None)
        return {"status": "cancelled", "message": "Initialization cancelled"}

    if inst["trader"] is None:
        _trader_instances.pop(user_id, None)
        raise HTTPException(409, "No trader running.")

    trader = inst["trader"]
    listener = inst["listener"]
    telegram_bot = inst.get("telegram_bot")

    try:
        from exchange.binance_rest import BinanceAPIError
        try:
            positions = trader.binance.get_position(trader.symbol)
            pos_qty = abs(float(positions.get("positionAmt", 0)))
            if pos_qty > 0:
                if float(positions.get("positionAmt", 0)) > 0:
                    close_side = "SELL"
                else:
                    close_side = "BUY"
                trader.binance.market_order(trader.symbol, close_side, pos_qty, reduce_only=True)
        except Exception:
            pass
    except Exception:
        pass

    trader.running = False
    listener.stop()
    if telegram_bot:
        telegram_bot.stop()
    trader.save_config(CONFIG_PATH)

    db = get_db()
    if db and user_id and hasattr(trader, '_save_full_state_to_db'):
        try:
            trader._save_full_state_to_db()
        except Exception as e:
            print(f"[Server] Failed to save model state: {e}")

    _trader_instances.pop(user_id, None)

    return {"status": "stopped", "trades": trader.trades, "pnl_pct": round(trader.total_pnl * 100, 2)}

@app.get("/api/v1/trader/status")
def trader_status(x_access_code: str = Header("")):
    user_id = verify_access(x_access_code)
    inst = _get_instance(user_id)

    if inst is None:
        return {"running": False, "symbol": "", "leverage": 1, "equity": 0, "candles": 0, "trades": 0, "wins": 0, "position": "FLAT", "unrealized_pnl_pct": 0}

    if inst["initializing"]:
        return {"running": False, "initializing": True, "symbol": "", "leverage": 1, "equity": 0, "candles": 0, "trades": 0, "wins": 0, "position": "FLAT", "unrealized_pnl_pct": 0}
    if inst["init_error"]:
        return {"running": False, "initializing": False, "error": inst["init_error"], "symbol": "", "leverage": 1, "equity": 0, "candles": 0, "trades": 0, "wins": 0, "position": "FLAT", "unrealized_pnl_pct": 0}
    if inst["trader"] is None:
        return {"running": False, "symbol": "", "leverage": 1, "equity": 0, "candles": 0, "trades": 0, "wins": 0, "position": "FLAT", "unrealized_pnl_pct": 0}

    t = inst["trader"]
    pos = getattr(t, 'pos', 0)
    entry_price = getattr(t, 'entry_price', 0)
    unrealized_pnl = 0.0
    if pos != 0 and entry_price > 0 and t.last_close > 0:
        pnl_raw = (t.last_close - entry_price) / entry_price
        unrealized_pnl = round(pnl_raw * t.leverage * (1 if pos == 1 else -1) * 100, 2)
    return {
        "running": True,
        "symbol": t.symbol,
        "leverage": t.leverage,
        "equity": round(t.equity, 2),
        "candles": t.candle_count,
        "trades": t.trades,
        "wins": t.wins,
        "position": "LONG" if pos == 1 else "SHORT" if pos == -1 else "FLAT",
        "unrealized_pnl_pct": unrealized_pnl,
    }

# ── Health ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "time": time.time(), "active_traders": len(_trader_instances), "max_traders": MAX_TRADERS}

# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=os.getenv("DEV", "0") == "1")