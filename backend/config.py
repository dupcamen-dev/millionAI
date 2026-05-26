import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        self.access_code = os.getenv("ACCESS_CODE", "")
        self.symbol = os.getenv("SYMBOL", "SAGAUSDT")
        self.leverage = int(os.getenv("LEVERAGE", "4"))
        self.mode = os.getenv("MODE", "paper")
        self.lr = float(os.getenv("LR", "0.01"))
        self.tau = float(os.getenv("TAU", "24.0"))
        self.sl = float(os.getenv("SL", "0.05"))
        self.tp = float(os.getenv("TP", "0.12"))
        self.config_file = os.getenv("CONFIG_FILE", "")
        self.telegram_token = os.getenv("TELEGRAM_TOKEN", "")

    @classmethod
    def from_cli(cls, args):
        c = cls()
        if args.symbol:
            c.symbol = args.symbol
        if args.leverage:
            c.leverage = args.leverage
        if args.mode:
            c.mode = args.mode
        if args.access_code:
            c.access_code = args.access_code
        if args.config:
            c.config_file = args.config
        if args.telegram:
            c.telegram_token = args.telegram
        if args.lr:
            c.lr = args.lr
        if args.tau:
            c.tau = args.tau
        if args.sl:
            c.sl = args.sl
        if args.tp:
            c.tp = args.tp
        return c
