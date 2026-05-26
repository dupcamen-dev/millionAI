import hashlib
import hmac
import json
import time
import urllib.request
import urllib.error
import urllib.parse

FAPI_BASE = "https://fapi.binance.com"

class BinanceAPIError(RuntimeError):
    def __init__(self, code: int, message: str, raw_body: str = ""):
        self.code = code
        self.message = message
        self.raw_body = raw_body
        super().__init__(f"[{code}] {message}")

    @classmethod
    def from_response(cls, body: str):
        try:
            data = json.loads(body)
            return cls(data.get("code", 0), data.get("msg", body), body)
        except json.JSONDecodeError:
            return cls(0, body, body)

BALANCE_ERR_CODES = {-2019, -2018, -2015, -1015, -2011, -2010, -2012, -2021, -2022}
INSUFFICIENT_BALANCE = -2019
INSUFFICIENT_MARGIN = -2021
INVALID_API_KEY = -2015
RATE_LIMIT = -1015
ORDER_REJECTED = -2011

class BinanceFuturesAPI:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self._exchange_info_cache = None
        self._exchange_info_ts = 0
        self._time_offset = 0
        self._sync_time()

    def _sync_time(self):
        """Fetch Binance server time and compute local offset."""
        try:
            url = f"{FAPI_BASE}/fapi/v1/time"
            with urllib.request.urlopen(url, timeout=10) as r:
                server_ms = json.loads(r.read())["serverTime"]
            local_ms = int(time.time() * 1000)
            self._time_offset = server_ms - local_ms
            print(f"[Binance] Time offset: {self._time_offset}ms")
        except Exception as e:
            print(f"[Binance] Time sync failed: {e}, using 0 offset")

    def _sign(self, params: dict) -> str:
        params["timestamp"] = int(time.time() * 1000) + self._time_offset
        params["recvWindow"] = 5000
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    def _request(self, method: str, path: str, signed: bool = False, params: dict = None) -> dict:
        params = params or {}
        if signed:
            query = self._sign(params)
            url = f"{FAPI_BASE}{path}?{query}"
        else:
            url = f"{FAPI_BASE}{path}"
            if params:
                url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method=method)
        req.add_header("X-MBX-APIKEY", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            err = BinanceAPIError.from_response(body)
            raise err
        except urllib.error.URLError as e:
            raise BinanceAPIError(0, f"Network error: {e.reason}")

    def get_balance(self) -> float:
        resp = self._request("GET", "/fapi/v2/account", signed=True)
        for asset in resp.get("assets", []):
            if asset["asset"] == "USDT":
                return float(asset["walletBalance"])
        return 0.0

    def get_position(self, symbol: str) -> dict:
        resp = self._request("GET", "/fapi/v2/positionRisk", signed=True, params={"symbol": symbol.upper()})
        if isinstance(resp, list) and len(resp) > 0:
            return resp[0]
        return {}

    def get_positions(self) -> list:
        resp = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        if isinstance(resp, list):
            return [p for p in resp if abs(float(p.get("positionAmt", 0))) > 0]
        return []

    def set_leverage(self, symbol: str, leverage: int):
        return self._request("POST", "/fapi/v1/leverage", signed=True, params={"symbol": symbol.upper(), "leverage": leverage})

    def market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def limit_order(self, symbol: str, side: str, quantity: float, price: float, reduce_only: bool = False) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": quantity,
            "price": price,
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def cancel_all(self, symbol: str):
        return self._request("DELETE", "/fapi/v1/openOrders", signed=True, params={"symbol": symbol.upper()})

    def get_open_orders(self, symbol: str = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/fapi/v1/openOrders", signed=True, params=params)

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 500) -> list:
        params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1500)}
        return self._request("GET", "/fapi/v1/klines", signed=False, params=params)

    def get_exchange_info(self) -> dict:
        now = time.time()
        if self._exchange_info_cache and now - self._exchange_info_ts < 300:
            return self._exchange_info_cache
        info = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
        self._exchange_info_cache = info
        self._exchange_info_ts = now
        return info

    def get_ticker(self, symbol: str = None) -> dict:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        resp = self._request("GET", "/fapi/v1/ticker/24hr", signed=False, params=params)
        if symbol:
            return resp if isinstance(resp, dict) else {}
        return resp if isinstance(resp, list) else []
