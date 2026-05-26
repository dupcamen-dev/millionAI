"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

interface Log {
  time: string;
  text: string;
  type: "sys" | "ai" | "exec" | "ok" | "err";
}

export default function AdminPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [equity] = useState(10.0);
  const [balance] = useState(10.0);
  const [logs, setLogs] = useState<Log[]>([
    { time: new Date().toLocaleTimeString(), text: "WebSocket connection established.", type: "sys" },
    { time: new Date().toLocaleTimeString(), text: "Neural network initialized. 16 neurons active.", type: "ai" },
    { time: new Date().toLocaleTimeString(), text: "Awaiting market data...", type: "sys" },
  ]);
  const [command, setCommand] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem("MILLION_ACCESS_CODE");
    if (stored !== "1231") {
      router.push("/access");
    } else {
      setAuthorized(true);
    }
  }, [router]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = command.trim().toLowerCase();
    if (!cmd) return;

    addLog("sys", `$ ${cmd}`);

    switch (cmd) {
      case "/status":
        addLog("sys", `Equity: $${equity.toFixed(2)} | Balance: $${balance.toFixed(2)}`);
        break;
      case "/help":
        addLog("sys", "Commands: /status, /summary, /trades, /help");
        break;
      default:
        addLog("err", `Unknown command: ${cmd}`);
    }
    setCommand("");
  };

  const addLog = (type: Log["type"], text: string) => {
    setLogs((prev) => [
      ...prev.slice(-49),
      { time: new Date().toLocaleTimeString(), text, type },
    ]);
  };

  if (!authorized) return null;

  const mockPositions = [
    { symbol: "BTC-PERP", size: "12.500", entry: "62,100.00", mark: "64,250.00", pnl: "+$26,875.00", dir: "long" },
    { symbol: "ETH-PERP", size: "150.00", entry: "3,400.50", mark: "3,450.25", pnl: "+$7,462.50", dir: "long" },
    { symbol: "SOL-PERP", size: "-500.00", entry: "145.20", mark: "142.10", pnl: "+$1,550.00", dir: "short" },
    { symbol: "LINK-PERP", size: "2,000.00", entry: "18.40", mark: "19.20", pnl: "+$1,600.00", dir: "long" },
  ];

  return (
    <div className="min-h-screen bg-background text-on-surface font-body-lg flex flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <aside className="bg-background hidden lg:flex flex-col border-r border-outline-variant w-64 shrink-0">
          <div className="p-unit-4 border-b border-outline-variant mb-unit-4">
            <div className="font-headline-md text-headline-md text-primary-fixed-dim mb-unit-1 uppercase">CONSOLE_V1.0</div>
            <div className="font-code-snippet text-code-snippet text-outline uppercase">ID: ROOT_USER</div>
          </div>
          <nav className="flex flex-col font-label-caps text-label-caps w-full">
            <span className="bg-primary-fixed-dim text-on-primary flex items-center gap-unit-2 px-unit-4 py-unit-2 uppercase w-full">
              TERMINAL
            </span>
            <span className="text-primary-fixed-dim flex items-center gap-unit-2 px-unit-4 py-unit-2 hover:bg-surface-variant transition-colors uppercase w-full cursor-pointer">
              ASSETS
            </span>
            <span className="text-primary-fixed-dim flex items-center gap-unit-2 px-unit-4 py-unit-2 hover:bg-surface-variant transition-colors uppercase w-full cursor-pointer">
              STRATEGY
            </span>
            <span className="text-primary-fixed-dim flex items-center gap-unit-2 px-unit-4 py-unit-2 hover:bg-surface-variant transition-colors uppercase w-full cursor-pointer">
              LOGS
            </span>
          </nav>
        </aside>

        <main className="flex-1 overflow-y-auto p-margin-mobile md:p-margin-desktop bg-surface-container-lowest">
          <div className="max-w-7xl mx-auto space-y-unit-8">
            <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
              <div>
                <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">Overview</h1>
                <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; SYS.STATUS: OPTIMAL</p>
              </div>
              <div className="font-label-caps text-label-caps text-primary-fixed-dim border border-primary-fixed-dim px-unit-2 py-unit-1 animate-pulse uppercase">
                LIVE
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
              <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
                <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
                <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Total Balance (Futures)</div>
                <div className="font-display text-display text-primary-fixed-dim">${balance.toFixed(2)}</div>
                <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-2 flex items-center gap-unit-1">
                  <span className="text-primary-fixed-dim">+</span>
                  +0.0% (24h)
                </div>
              </div>
              <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
                <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
                <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Equity</div>
                <div className="font-display text-display text-primary-fixed-dim">${equity.toFixed(2)}</div>
                <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-2 flex items-center gap-unit-1">
                  <span className="text-primary-fixed-dim">+</span>
                  +0.0% (24h)
                </div>
              </div>
              <div className="border border-surface-variant p-unit-4 bg-background hover:border-primary-fixed-dim transition-colors group relative">
                <div className="absolute top-0 right-0 w-2 h-2 bg-primary-fixed-dim m-unit-1 opacity-50 group-hover:opacity-100 transition-opacity" />
                <div className="font-label-caps text-label-caps text-outline mb-unit-2 uppercase">Unrealized PnL</div>
                <div className="font-display text-display text-primary-fixed-dim">$145,521.55</div>
                <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-2 flex items-center gap-unit-1">
                  <span className="text-outline">~</span>
                  Active Positions: 4
                </div>
              </div>
            </div>

            <div className="border border-surface-variant bg-background">
              <div className="p-unit-4 border-b border-surface-variant flex justify-between items-center bg-surface-container-low">
                <h2 className="font-label-caps text-label-caps text-on-surface uppercase">OPEN_POSITIONS</h2>
                <button className="font-code-snippet text-code-snippet text-primary-fixed-dim border border-surface-variant px-unit-2 py-unit-1 hover:bg-primary-fixed-dim hover:text-on-primary transition-colors uppercase">
                  CLOSE_ALL
                </button>
              </div>
              <div className="w-full overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-surface-variant font-label-caps text-label-caps text-outline">
                      <th className="p-unit-4 uppercase font-normal">ASSET</th>
                      <th className="p-unit-4 uppercase font-normal text-right">SIZE</th>
                      <th className="p-unit-4 uppercase font-normal text-right">ENTRY</th>
                      <th className="p-unit-4 uppercase font-normal text-right">MARK_PRICE</th>
                      <th className="p-unit-4 uppercase font-normal text-right">PNL</th>
                    </tr>
                  </thead>
                  <tbody className="font-code-snippet text-code-snippet text-on-surface">
                    {mockPositions.map((p, i) => (
                      <tr key={i} className="border-b border-surface-variant hover:bg-surface-container-low transition-colors group">
                        <td className="p-unit-4 flex items-center gap-unit-2">
                          <div className={`w-2 h-2 ${p.dir === "long" ? "bg-primary-fixed-dim" : "bg-error"}`} />
                          {p.symbol}
                        </td>
                        <td className="p-unit-4 text-right">{p.size}</td>
                        <td className="p-unit-4 text-right">{p.entry}</td>
                        <td className="p-unit-4 text-right">{p.mark}</td>
                        <td className="p-unit-4 text-right text-primary-fixed-dim group-hover:font-bold">{p.pnl}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="border border-surface-variant bg-background flex flex-col">
              <div className="p-unit-4 border-b border-surface-variant flex justify-between items-center bg-surface-container-low">
                <h2 className="font-label-caps text-label-caps text-on-surface uppercase">SYS.LOG_STREAM</h2>
                <div className="flex gap-unit-2">
                  <span className="w-3 h-3 border border-outline-variant bg-background" />
                  <span className="w-3 h-3 border border-outline-variant bg-background" />
                  <span className="w-3 h-3 border border-outline-variant bg-primary-fixed-dim" />
                </div>
              </div>
              <div ref={logRef} className="h-48 overflow-y-auto p-unit-4 font-code-snippet text-code-snippet text-on-surface-variant flex flex-col gap-unit-1 bg-surface-container-lowest">
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
          </div>
        </main>
      </div>
      <Footer />
    </div>
  );
}
