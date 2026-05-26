"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { apiGet, apiPost, BalanceData, TraderStatus, TraderStartResult, LogEntry, LogsData } from "@/lib/api";

interface LocalLog {
  time: string;
  text: string;
  type: "sys" | "ai" | "exec" | "ok" | "err";
}

export default function TerminalPage() {
  const [equity, setEquity] = useState(0);
  const [balance, setBalance] = useState(0);
  const [positions, setPositions] = useState<BalanceData["positions"]>([]);
  const [traderStatus, setTraderStatus] = useState<TraderStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [logs, setLogs] = useState<LocalLog[]>([
    { time: new Date().toLocaleTimeString(), text: "Connecting to API...", type: "sys" },
  ]);
  const [command, setCommand] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const addLog = useCallback((type: LocalLog["type"], text: string) => {
    setLogs((prev) => [
      ...prev.slice(-49),
      { time: new Date().toLocaleTimeString(), text, type },
    ]);
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await apiGet<BalanceData>("/api/v1/balance");
        setEquity(data.equity);
        setBalance(data.balance);
        setPositions(data.positions);
      } catch {
        addLog("err", "Failed to load balance from API");
      }
    };
    const loadStatus = async () => {
      try {
        const s = await apiGet<TraderStatus>("/api/v1/trader/status");
        setTraderStatus(s);
      } catch {}
    };
    load();
    loadStatus();
    const interval = setInterval(() => { load(); loadStatus(); }, 15000);
    return () => clearInterval(interval);
  }, [addLog]);

  // Poll server logs and merge into local log stream
  const [lastLogId, setLastLogId] = useState(0);
  useEffect(() => {
    const poll = async () => {
      try {
        const data = await apiGet<LogsData>(`/api/v1/logs?limit=20`);
        const newLogs = data.logs.filter((l) => l.id > lastLogId);
        if (newLogs.length > 0) {
          setLastLogId(newLogs[newLogs.length - 1].id);
          newLogs.forEach((l) => {
            const type = l.level === "ERROR" || l.level === "BALANCE" ? "err" : "ok";
            addLog(type, l.message);
          });
        }
      } catch {}
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [lastLogId, addLog]);

  const handleStart = async () => {
    setStarting(true);
    addLog("sys", "Starting trader...");
    try {
      const r = await apiPost<TraderStartResult>("/api/v1/trader/start");
      addLog("ok", `Trader started: ${r.symbol} ${r.leverage}x balance=$${r.balance}`);
      if (r.candidates && r.candidates.length > 0) {
        r.candidates.forEach((c: any, i: number) => {
          addLog("sys", `  #${i+1} ${c.symbol} @ $${c.price} vol=${c.volatility}%`);
        });
      }
      setTraderStatus({ running: true, symbol: r.symbol, leverage: r.leverage, equity: r.balance, candles: 0, trades: 0, wins: 0 });
    } catch (e: any) {
      addLog("err", `Start failed: ${e.message}`);
    }
    setStarting(false);
  };

  const handleStop = async () => {
    setStopping(true);
    addLog("sys", "Stopping trader & closing positions...");
    try {
      const r = await apiPost<{ status: string; trades: number; pnl_pct: number }>("/api/v1/trader/stop");
      addLog("ok", `Trader stopped. Trades: ${r.trades} PnL: ${r.pnl_pct}%`);
      setTraderStatus(null);
    } catch (e: any) {
      addLog("err", `Stop failed: ${e.message}`);
    }
    setStopping(false);
  };

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = command.trim().toLowerCase();
    if (!cmd) return;
    addLog("sys", `$ ${cmd}`);
    switch (cmd) {
      case "/status":
        addLog("sys", `Equity: $${equity.toFixed(2)} | Balance: $${balance.toFixed(2)}`);
        if (traderStatus?.running) addLog("sys", `Trader: ${traderStatus.symbol} ${traderStatus.leverage}x | Candles: ${traderStatus.candles} | Trades: ${traderStatus.trades}`);
        break;
      case "/help":
        addLog("sys", "Commands: /status, /positions, /help");
        break;
      case "/positions":
        if (positions.length === 0) addLog("sys", "No open positions");
        else positions.forEach((p) => addLog("exec", `${p.side} ${p.symbol} qty=${p.quantity}`));
        break;
      default:
        addLog("err", `Unknown: ${cmd}`);
    }
    setCommand("");
  };

  const totalPnl = positions.reduce((sum, p) => sum + (p.pnl || 0), 0);

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div className="flex items-end gap-unit-4">
          <div>
            <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">TERMINAL</h1>
            <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">
              &gt; {traderStatus?.running ? `TRADING ${traderStatus.symbol} ${traderStatus.leverage}x` : "SYS.IDLE"}
            </p>
          </div>
          {traderStatus?.running && (
            <div className="font-label-caps text-label-caps text-primary-fixed-dim border border-primary-fixed-dim px-unit-2 py-unit-1 animate-pulse uppercase">
              LIVE
            </div>
          )}
        </div>
        <div className="flex gap-unit-2">
          <button
            onClick={handleStart}
            disabled={starting || traderStatus?.running}
            className={`font-label-caps text-label-caps px-unit-4 py-unit-2 border transition-colors uppercase ${
              traderStatus?.running
                ? "border-outline-variant text-outline cursor-not-allowed"
                : "border-primary-fixed-dim text-primary-fixed-dim hover:bg-primary-fixed-dim hover:text-on-primary"
            }`}
          >
            {starting ? "[ STARTING ]" : "[ START ]"}
          </button>
          <button
            onClick={handleStop}
            disabled={stopping || !traderStatus?.running}
            className={`font-label-caps text-label-caps px-unit-4 py-unit-2 border transition-colors uppercase ${
              !traderStatus?.running
                ? "border-outline-variant text-outline cursor-not-allowed"
                : "border-error text-error hover:bg-error hover:text-on-error"
            }`}
          >
            {stopping ? "[ STOPPING ]" : "[ STOP ]"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-gutter">
        <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
          <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
          <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Balance</div>
          <div className="font-display text-display text-primary-fixed-dim">${balance.toFixed(2)}</div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
          <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
          <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Equity</div>
          <div className="font-display text-display text-primary-fixed-dim">${equity.toFixed(2)}</div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
          <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
          <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Unrealized PnL</div>
          <div className="font-display text-display text-primary-fixed-dim">${totalPnl.toFixed(2)}</div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
          <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
          <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Trader</div>
          <div className="font-display text-display" style={{ fontSize: "1.4rem", color: traderStatus?.running ? "#28a745" : "#666" }}>
            {traderStatus?.running ? "RUNNING" : "STOPPED"}
          </div>
          <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-2">
            {traderStatus?.running
              ? `${traderStatus.symbol} ${traderStatus.leverage}x | Candles: ${traderStatus.candles}`
              : "No active trader"}
          </div>
        </div>
      </div>

      <div className="border border-surface-variant bg-background">
        <div className="p-unit-4 border-b border-surface-variant flex justify-between items-center bg-surface-container-low">
          <h2 className="font-label-caps text-label-caps text-on-surface uppercase">OPEN_POSITIONS</h2>
        </div>
        <div className="w-full overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-surface-variant font-label-caps text-label-caps text-outline">
                <th className="p-unit-4 uppercase font-normal">ASSET</th>
                <th className="p-unit-4 uppercase font-normal text-right">SIDE</th>
                <th className="p-unit-4 uppercase font-normal text-right">SIZE</th>
                <th className="p-unit-4 uppercase font-normal text-right">ENTRY</th>
                <th className="p-unit-4 uppercase font-normal text-right">PNL</th>
              </tr>
            </thead>
            <tbody className="font-code-snippet text-code-snippet text-on-surface">
              {positions.length === 0 ? (
                <tr><td colSpan={5} className="p-unit-4 text-center text-outline">No open positions</td></tr>
              ) : (
                positions.map((p, i) => (
                  <tr key={i} className="border-b border-surface-variant hover:bg-surface-container-low transition-colors group">
                    <td className="p-unit-4 flex items-center gap-unit-2">
                      <div className={`w-2 h-2 ${p.side === "BUY" ? "bg-primary-fixed-dim" : "bg-error"}`} />
                      {p.symbol}
                    </td>
                    <td className="p-unit-4 text-right">{p.side}</td>
                    <td className="p-unit-4 text-right">{p.quantity}</td>
                    <td className="p-unit-4 text-right">${p.entry_price?.toFixed(4)}</td>
                    <td className="p-unit-4 text-right text-primary-fixed-dim">${(p.pnl || 0).toFixed(2)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="border border-surface-variant bg-background flex flex-col">
        <div className="p-unit-4 border-b border-surface-variant flex justify-between items-center bg-surface-container-low">
          <h2 className="font-label-caps text-label-caps text-on-surface uppercase">SYS.LOG_STREAM</h2>
        </div>
        <div ref={logRef} className="h-64 overflow-y-auto p-unit-4 font-code-snippet text-code-snippet text-on-surface-variant flex flex-col gap-unit-1 bg-surface-container-lowest">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-unit-2">
              <span className="text-outline shrink-0">{log.time}</span>
              <span className="text-primary-fixed-dim shrink-0">&gt;</span>
              <span className={log.type === "err" ? "text-error" : log.type === "ok" ? "text-primary-fixed-dim" : ""}>
                {log.text}
              </span>
            </div>
          ))}
          <span className="text-primary-fixed-dim animate-pulse">_</span>
        </div>
        <form onSubmit={handleCommand} className="p-unit-2 border-t border-surface-variant bg-background flex items-center gap-unit-2">
          <span className="text-primary-fixed-dim font-code-snippet pl-unit-2">$</span>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            className="bg-transparent border-none text-on-surface font-code-snippet text-code-snippet w-full focus:ring-0 focus:outline-none placeholder:text-outline"
            placeholder="Enter command..."
            type="text"
          />
        </form>
      </div>
    </>
  );
}
