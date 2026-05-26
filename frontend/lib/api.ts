const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function headers(): Record<string, string> {
  const code = typeof window !== "undefined" ? localStorage.getItem("MILLION_ACCESS_CODE") : "";
  return {
    "Content-Type": "application/json",
    "X-Access-Code": code || "",
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: headers() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface BalanceData {
  equity: number;
  balance: number;
  positions: PositionData[];
}

export interface PositionData {
  symbol: string;
  side: string;
  entry_price: number;
  quantity: number;
  leverage: number;
  pnl?: number;
}

export interface LogEntry {
  created_at: string;
  level: string;
  message: string;
  id: number;
}

export interface LogsData {
  logs: LogEntry[];
  total: number;
}

export interface ScreenerAsset {
  symbol: string;
  price: number;
  volume: number;
  volatility: number;
  score: number;
}

export interface StrategyData {
  neurons: number[][];
  symbol?: string;
  leverage?: number;
}

export interface ApiKeysData {
  api_key: string;
  api_secret: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
}
