import json
import queue
import threading
import time
import urllib.request
import urllib.error

class TelegramBot:
    def __init__(self, token: str, msg_queue: queue.Queue):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_ids = set()
        self.offset = 0
        self.running = True
        self.msg_queue = msg_queue

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
        text = text.strip().lower()
        if text == "/start":
            self.send(chat_id, "SNN Crypto Trader v1.0\nCommands:\n/status\n/summary\n/help")
        elif text == "/help":
            self.send(chat_id, "/status - current state\n/summary - trade stats\n/help - this message")
        else:
            self.send(chat_id, f"Unknown: {text}")

    def stop(self):
        self.running = False
