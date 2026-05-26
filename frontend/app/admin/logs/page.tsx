"use client";

import { useState, useRef, useEffect } from "react";

interface LogEntry {
  time: string;
  level: "INFO" | "WARN" | "ERROR" | "EXEC" | "SYS";
  message: string;
}

function generateMockLogs(): LogEntry[] {
  const messages: LogEntry[] = [];
  const levels: LogEntry["level"][] = ["INFO", "SYS", "EXEC", "WARN", "ERROR"];
  const sysMessages = [
    "WebSocket connection established.",
    "Neural network initialized. 16 neurons active.",
    "Market data stream: SAGAUSDT@kline_5m",
    "Weight matrix loaded from best_config.json",
    "R-STDP micro-reward engine enabled.",
    "Epsilon-greedy: 0.150 -> 0.020 anneal complete.",
    "Bias=1.0, membrane decay=0.99, adaptive LR active.",
    "Asset screener: scanning Binance Futures...",
    "Synapse count: 1024 active connections.",
    "Memory pool: 4096 KB allocated.",
    "Event queue: 0 pending events.",
    "Heartbeat check: OK",
    "Telegram bot registered successfully.",
    "No position to close. Awaiting signal.",
    "SYS_REF sync: 0x71C",
  ];
  const execMessages = [
    "BUY 0.5 SAGAUSDT @ $2.842",
    "SELL 0.3 SOLUSDT @ $142.10",
    "CLOSE BTC-PERP @ $64,250.00 PnL: +$26,875.00",
    "LEVERAGE: 4x SET",
    "SL/TP updated",
  ];
  const warnMessages = [
    "Eligibility trace decay: tau approaching threshold",
    "Spike rate > 0.8 in N3, check saturation",
    "Market volatility spike detected",
  ];
  const errorMessages = [
    "WebSocket reconnect attempt 3/5",
    "Order rejected: insufficient margin",
    "Rate limit approaching",
  ];

  const now = new Date();
  for (let i = 120; i >= 0; i--) {
    const t = new Date(now.getTime() - i * 5000);
    const timeStr = t.toLocaleTimeString();
    let level: LogEntry["level"];
    let message: string;

    if (i % 30 === 0) {
      level = "ERROR";
      message = errorMessages[Math.floor(Math.random() * errorMessages.length)];
    } else if (i % 15 === 0) {
      level = "WARN";
      message = warnMessages[Math.floor(Math.random() * warnMessages.length)];
    } else if (i % 7 === 0) {
      level = "EXEC";
      message = execMessages[Math.floor(Math.random() * execMessages.length)];
    } else if (i % 3 === 0) {
      level = "SYS";
      message = sysMessages[Math.floor(Math.random() * sysMessages.length)];
    } else {
      level = "INFO";
      message = sysMessages[Math.floor(Math.random() * sysMessages.length)];
    }

    messages.push({ time: timeStr, level, message });
  }
  return messages;
}

const ALL_LOGS = generateMockLogs();
const LEVELS: (LogEntry["level"] | "ALL")[] = ["ALL", "SYS", "INFO", "EXEC", "WARN", "ERROR"];

const LEVEL_COLORS: Record<LogEntry["level"], string> = {
  INFO: "text-on-surface-variant",
  SYS: "text-primary-fixed-dim",
  EXEC: "text-on-surface",
  WARN: "text-[#ffd5ae]",
  ERROR: "text-error",
};

export default function LogsPage() {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const filtered = ALL_LOGS.filter((l) => {
    if (levelFilter !== "ALL" && l.level !== levelFilter) return false;
    if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [filtered.length, autoScroll]);

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">LOGS</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; SYS.LOG_TAIL: {ALL_LOGS.length} ENTRIES</p>
        </div>
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`font-label-caps text-label-caps px-unit-4 py-unit-2 border transition-colors uppercase ${
            autoScroll
              ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
              : "border-outline-variant text-outline"
          }`}
        >
          AUTO_SCROLL: {autoScroll ? "ON" : "OFF"}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-unit-4 items-start md:items-center justify-between">
        <div className="flex gap-unit-2 font-label-caps text-label-caps flex-wrap">
          {LEVELS.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
                levelFilter === lvl
                  ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
                  : "border-outline-variant text-outline hover:border-primary-fixed-dim"
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full md:w-64"
          placeholder="Search logs..."
        />
      </div>

      <div className="border border-surface-variant bg-background">
        <div className="p-unit-2 border-b border-surface-variant bg-surface-container-low font-code-snippet text-code-snippet text-outline flex items-center gap-unit-4 uppercase">
          <span className="w-16 shrink-0">TIME</span>
          <span className="w-16 shrink-0">LEVEL</span>
          <span className="flex-1">MESSAGE</span>
        </div>
        <div ref={logContainerRef} className="h-[500px] overflow-y-auto font-code-snippet text-code-snippet">
          {filtered.length === 0 ? (
            <div className="p-unit-8 text-center text-outline">&gt; NO LOGS MATCH FILTER</div>
          ) : (
            filtered.map((log, i) => (
              <div
                key={i}
                className="flex items-start gap-unit-4 px-unit-4 py-unit-2 border-b border-surface-variant hover:bg-surface-container-low transition-colors"
              >
                <span className="text-outline w-16 shrink-0">{log.time}</span>
                <span className={`${LEVEL_COLORS[log.level]} w-16 shrink-0 font-bold uppercase`}>
                  {log.level}
                </span>
                <span className={`flex-1 ${log.level === "ERROR" ? "text-error" : ""}`}>
                  &gt; {log.message}
                </span>
              </div>
            ))
          )}
        </div>
        <div className="p-unit-2 border-t border-surface-variant bg-surface-container-low font-code-snippet text-code-snippet text-outline text-right">
          {filtered.length} / {ALL_LOGS.length} ENTRIES
        </div>
      </div>
    </>
  );
}
