#!/usr/bin/env python3
"""Million SNN Crypto Trader — Entry Point

Usage:
    python main.py --mode paper --symbol SAGAUSDT    # paper trade
    python main.py --mode real --access-code 1231     # real trade, keys from Supabase
    python main.py --mode real --api-key X --api-secret Y   # real trade with direct keys
    python main.py --mode real --auto-symbol 1              # real trade with screener + auto symbol/leverage
"""
import argparse
import os
import sys
import queue
import threading

# Add backend directory to sys.path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description="Million SNN Crypto Trader")
    parser.add_argument("--mode", default=os.getenv("MODE", "paper"), choices=["paper", "real"])
    parser.add_argument("--symbol", default=os.getenv("SYMBOL", "SAGAUSDT"))
    parser.add_argument("--leverage", type=int, default=int(os.getenv("LEVERAGE", "4")))
    parser.add_argument("--access-code", default=os.getenv("ACCESS_CODE", ""))
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--api-secret", default=os.getenv("API_SECRET", ""))
    parser.add_argument("--config", default=os.getenv("CONFIG_FILE", ""))
    parser.add_argument("--telegram", default=os.getenv("TELEGRAM_TOKEN", ""))
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--tau", type=float, default=24.0)
    parser.add_argument("--sl", type=float, default=0.05)
    parser.add_argument("--tp", type=float, default=0.12)
    parser.add_argument("--auto-symbol", default=os.getenv("AUTO_SYMBOL", ""))
    parser.add_argument("--supabase-url", default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--supabase-key", default=os.getenv("SUPABASE_SERVICE_KEY", ""))
    args = parser.parse_args()

    db = None
    user_id = None
    api_key = args.api_key
    api_secret = args.api_secret

    # If access code is given, try to load keys from Supabase
    if args.access_code and args.supabase_url and args.supabase_key:
        from db.supabase import SupabaseDB
        db = SupabaseDB(args.supabase_url, args.supabase_key)
        user = db.get_user_by_access_code(args.access_code)
        if user:
            user_id = user["id"]
            print(f"[Main] User found: {user_id}")
            keys = db.get_api_keys(user_id)
            if keys:
                api_key = keys.get("api_key", api_key)
                api_secret = keys.get("api_secret", api_secret)
                if not args.telegram:
                    args.telegram = keys.get("telegram_bot_token", "")

    # Telegram bot thread
    msg_queue = None
    telegram_thread = None
    if args.telegram:
        from telegram.bot import TelegramBot
        msg_queue = queue.Queue()
        bot = TelegramBot(args.telegram, msg_queue)
        telegram_thread = threading.Thread(target=bot.run, daemon=True)
        telegram_thread.start()
        if msg_queue:
            msg_queue.put(f"Trader starting: {args.symbol} {args.mode} {args.leverage}x")

    # Create trader
    if args.mode == "real":
        if not api_key or not api_secret:
            print("Error: --api-key and --api-secret required for real mode (or set ACCESS_CODE + Supabase)")
            sys.exit(1)
        from trader.real import RealTrader
        auto_sym = args.auto_symbol.lower() in ("1", "true", "yes", "on") if args.auto_symbol else (args.symbol == "")
        trader = RealTrader(
            api_key, api_secret,
            symbol=args.symbol, leverage=args.leverage,
            config_file=args.config or None,
            lr=args.lr, tau=args.tau, sl=args.sl, tp=args.tp,
            db=db, telegram_queue=msg_queue,
            auto_symbol=auto_sym,
        )
        if user_id:
            trader.set_user(user_id)
        trader._init_exchange()
    else:
        from trader.paper import PaperTrader
        trader = PaperTrader(
            symbol=args.symbol, leverage=args.leverage,
            config_file=args.config or None,
            lr=args.lr, tau=args.tau, sl=args.sl, tp=args.tp,
        )

    # Wire candle callback to DB sync
    original_on_candle = trader.on_candle
    def on_candle_with_db(o, h, l, c, v, ts):
        original_on_candle(o, h, l, c, v, ts)
        if hasattr(trader, 'sync_db_every_candle'):
            trader.sync_db_every_candle()
    trader.on_candle = on_candle_with_db

    # Start WebSocket
    from exchange.binance_ws import BinanceWSListener
    listener = BinanceWSListener(trader.on_candle)

    try:
        print(f"[Main] Starting {args.mode} trader: {args.symbol} {args.leverage}x")
        listener.connect(args.symbol, "5m")
    except KeyboardInterrupt:
        print("\n[Main] Shutting down...")
        trader.running = False
        listener.stop()
        trader.summary()
        save_path = args.config or os.path.join(os.path.dirname(__file__), "best_config.json")
        trader.save_config(save_path)
        print(f"[Main] Config saved to {save_path}")

if __name__ == "__main__":
    main()
