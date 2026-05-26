-- Million Terminal — Supabase Schema
-- Run this SQL in your Supabase SQL Editor to set up the database.

-- Users table (linked to Google OAuth)
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE,
  access_code TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  is_active BOOLEAN DEFAULT false
);

-- Binance API keys + Telegram config (encrypted at rest)
CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  api_key TEXT NOT NULL,
  api_secret TEXT NOT NULL,
  telegram_bot_token TEXT DEFAULT '',
  telegram_chat_id TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id)
);

-- Trades executed by the SNN
CREATE TABLE IF NOT EXISTS trades (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  entry_price DOUBLE PRECISION NOT NULL,
  exit_price DOUBLE PRECISION,
  quantity DOUBLE PRECISION NOT NULL,
  leverage INT DEFAULT 1,
  pnl DOUBLE PRECISION,
  pnl_pct DOUBLE PRECISION,
  close_reason TEXT,
  opened_at TIMESTAMPTZ DEFAULT now(),
  closed_at TIMESTAMPTZ
);

-- Equity curve (time series)
CREATE TABLE IF NOT EXISTS equity_curve (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  equity DOUBLE PRECISION NOT NULL,
  balance DOUBLE PRECISION NOT NULL,
  timestamp TIMESTAMPTZ DEFAULT now()
);

-- Real-time trading logs
CREATE TABLE IF NOT EXISTS logs (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  level TEXT DEFAULT 'info',
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_equity_user_id ON equity_curve(user_id);
CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_curve(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE equity_curve ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs ENABLE ROW LEVEL SECURITY;

-- RLS policies: users can only see their own data
CREATE POLICY user_own_data ON users
  FOR ALL USING (auth.uid() = id);

CREATE POLICY user_own_api_keys ON api_keys
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY user_own_trades ON trades
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY user_own_equity ON equity_curve
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY user_own_logs ON logs
  FOR ALL USING (auth.uid() = user_id);
