const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let _accessCode: string | null = null;

export function setAccessCode(code: string) { _accessCode = code; }
export function getAccessCode(): string | null { return _accessCode; }
export function clearAccessCode() { _accessCode = null; }

function headers(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Access-Code": _accessCode || "",
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: headers() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
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

export interface TraderStatus {
  running: boolean;
  initializing?: boolean;
  error?: string;
  symbol: string;
  leverage: number;
  equity: number;
  candles: number;
  trades: number;
  wins: number;
  position?: string;
  unrealized_pnl_pct?: number;
}

export interface TraderStartResult {
  status: string;
  symbol: string;
  leverage: number;
  balance: number;
  candidates?: ScreenerAsset[];
}
