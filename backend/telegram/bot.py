import json
import queue
import threading
import time
import urllib.request
import urllib.error


class TelegramBot:
    def __init__(self, token: str, msg_queue: queue.Queue, trader_ref=None):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_ids = set()
        self.offset = 0
        self.running = True
        self.msg_queue = msg_queue
        self._trader_ref = trader_ref

    def _req(self, method, data):
        url = f"{self.base}/{method}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def send(self, chat_id, text):
        self._req("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

    def broadcast(self, text):
        for cid in list(self.chat_ids):
            self.send(cid, text)

    def run(self):
        while self.running:
            try:
                url = f"{self.base}/getUpdates?offset={self.offset}&timeout=30"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=35) as r:
                    updates = json.loads(r.read()).get("result", [])
                for u in updates:
                    self.offset = u["update_id"] + 1
                    chat_id = u.get("message", {}).get("chat", {}).get("id")
                    if chat_id:
                        self.chat_ids.add(chat_id)
                        text = u["message"].get("text", "")
                        self._handle(chat_id, text)
            except Exception:
                pass
            while not self.msg_queue.empty():
                try:
                    self.broadcast(self.msg_queue.get_nowait())
                except queue.Empty:
                    break
            time.sleep(0.5)

    def _handle(self, chat_id, text):
        text = text.strip()
        cmd = text.lower().split()[0] if text else ""
        if cmd == "/start":
            self.send(chat_id, "<b>SNN Crypto Trader v1.0</b>\n\nCommands:\n/status — current state\n/positions — open positions\n/summary — trade stats\n/help — this message")
        elif cmd == "/help":
            self.send(chat_id, "<b>SNN Crypto Trader</b>\n\n/status — symbol, leverage, equity, candles\n/positions — open positions with PnL\n/summary — trades, winrate, total PnL\n/help — this message")
        elif cmd == "/status":
            self._cmd_status(chat_id)
        elif cmd == "/summary":
            self._cmd_summary(chat_id)
        elif cmd == "/positions":
            self._cmd_positions(chat_id)
        else:
            self.send(chat_id, f"Unknown command: {text}\nType /help for available commands.")

    def _get_trader(self):
        if self._trader_ref is None:
            return None
        if callable(self._trader_ref):
            return self._trader_ref()
        return self._trader_ref

    def _cmd_status(self, chat_id):
        t = self._get_trader()
        if not t:
            self.send(chat_id, "⚠️ Trader not running")
            return
        sym = getattr(t, 'symbol', '???')
        lev = getattr(t, 'leverage', 1)
        eq = getattr(t, 'equity', 0)
        candles = getattr(t, 'candle_count', 0)
        pos = getattr(t, 'pos', 0)
        pos_str = "FLAT" if pos == 0 else ("LONG" if pos == 1 else "SHORT")
        entry = getattr(t, 'entry_price', 0)
        msg = f"📊 <b>Status</b>\n"
        msg += f"Symbol: {sym}\n"
        msg += f"Leverage: {lev}x\n"
        msg += f"Equity: ${eq:.2f}\n"
        msg += f"Position: {pos_str}"
        if pos != 0 and entry:
            msg += f" @ ${entry:.4f}"
        msg += f"\nCandles: {candles}"
        self.send(chat_id, msg)

    def _cmd_summary(self, chat_id):
        t = self._get_trader()
        if not t:
            self.send(chat_id, "⚠️ Trader not running")
            return
        trades = getattr(t, 'trades', 0)
        wins = getattr(t, 'wins', 0)
        pnl = getattr(t, 'total_pnl', 0)
        eq = getattr(t, 'equity', 0)
        wr = (wins / trades * 100) if trades > 0 else 0
        sym = getattr(t, 'symbol', '???')
        msg = f"📈 <b>Summary</b>\n"
        msg += f"Symbol: {sym}\n"
        msg += f"Trades: {trades}\n"
        msg += f"Win Rate: {wr:.1f}%\n"
        msg += f"Total PnL: {pnl*100:.2f}%\n"
        msg += f"Equity: ${eq:.2f}"
        self.send(chat_id, msg)

    def _cmd_positions(self, chat_id):
        t = self._get_trader()
        if not t:
            self.send(chat_id, "⚠️ Trader not running")
            return
        pos = getattr(t, 'pos', 0)
        if pos == 0:
            self.send(chat_id, "📋 No open positions")
            return
        sym = getattr(t, 'symbol', '???')
        entry = getattr(t, 'entry_price', 0)
        lev = getattr(t, 'leverage', 1)
        side = "LONG" if pos == 1 else "SHORT"
        msg = f"📋 <b>Open Position</b>\n"
        msg += f"Symbol: {sym}\n"
        msg += f"Side: {side}\n"
        msg += f"Entry: ${entry:.4f}\n"
        msg += f"Leverage: {lev}x"
        self.send(chat_id, msg)

    def stop(self):
        self.running = False