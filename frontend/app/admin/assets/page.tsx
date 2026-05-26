"use client";

import { useState } from "react";

const SCREENED_ASSETS = [
  { symbol: "SAGAUSDT", price: 2.84, volume: 285_000_000, volatility: 3.2, risk: 1.54, signal: "BUY" },
  { symbol: "XANUSDT", price: 0.52, volume: 412_000_000, volatility: 4.1, risk: 2.10, signal: "NEUTRAL" },
  { symbol: "ESPORTSUSDT", price: 0.089, volume: 275_000_000, volatility: 5.8, risk: 2.45, signal: "SELL" },
  { symbol: "BTCUSDT", price: 64250, volume: 18_200_000_000, volatility: 1.8, risk: 0.90, signal: "NEUTRAL" },
  { symbol: "ETHUSDT", price: 3450, volume: 9_800_000_000, volatility: 2.1, risk: 1.05, signal: "BUY" },
  { symbol: "SOLUSDT", price: 142, volume: 3_400_000_000, volatility: 3.5, risk: 1.75, signal: "NEUTRAL" },
  { symbol: "LINKUSDT", price: 19.20, volume: 890_000_000, volatility: 2.8, risk: 1.40, signal: "SELL" },
  { symbol: "DOGEUSDT", price: 0.12, volume: 1_200_000_000, volatility: 4.5, risk: 2.25, signal: "NEUTRAL" },
];

const FILTERS = ["ALL", "BUY", "SELL", "NEUTRAL"];

export default function AssetsPage() {
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  const filtered = SCREENED_ASSETS.filter((a) => {
    if (filter !== "ALL" && a.signal !== filter) return false;
    if (search && !a.symbol.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">ASSETS</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; SCREENER.ACTIVE: 8 ASSETS</p>
        </div>
        <div className="font-label-caps text-label-caps text-primary-fixed-dim uppercase opacity-70">
          VOL &gt; $100M &nbsp;|&nbsp; PRICE &lt; $1000
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-unit-4 items-start md:items-center justify-between">
        <div className="flex gap-unit-2 font-label-caps text-label-caps">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
                filter === f
                  ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
                  : "border-outline-variant text-outline hover:border-primary-fixed-dim hover:text-primary-fixed-dim"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full md:w-64"
          placeholder="Search symbol..."
        />
      </div>

      <div className="border border-surface-variant bg-background">
        <div className="w-full overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-surface-variant font-label-caps text-label-caps text-outline">
                <th className="p-unit-4 uppercase font-normal">SYMBOL</th>
                <th className="p-unit-4 uppercase font-normal text-right">PRICE</th>
                <th className="p-unit-4 uppercase font-normal text-right">24h VOLUME</th>
                <th className="p-unit-4 uppercase font-normal text-right">VOLATILITY</th>
                <th className="p-unit-4 uppercase font-normal text-right">RISK SCORE</th>
                <th className="p-unit-4 uppercase font-normal text-center">SIGNAL</th>
              </tr>
            </thead>
            <tbody className="font-code-snippet text-code-snippet text-on-surface">
              {filtered.map((a) => (
                <tr key={a.symbol} className="border-b border-surface-variant hover:bg-surface-container-low transition-colors group">
                  <td className="p-unit-4 font-bold text-primary-fixed-dim">{a.symbol}</td>
                  <td className="p-unit-4 text-right">
                    {a.price >= 1000 ? `$${a.price.toLocaleString()}` : `$${a.price}`}
                  </td>
                  <td className="p-unit-4 text-right text-on-surface-variant">
                    ${(a.volume / 1_000_000).toFixed(0)}M
                  </td>
                  <td className="p-unit-4 text-right">{a.volatility.toFixed(1)}%</td>
                  <td className="p-unit-4 text-right">{a.risk.toFixed(2)}</td>
                  <td className="p-unit-4 text-center">
                    <span
                      className={`px-unit-2 py-unit-1 uppercase text-[11px] tracking-widest ${
                        a.signal === "BUY"
                          ? "bg-primary-fixed-dim text-on-primary"
                          : a.signal === "SELL"
                          ? "bg-error text-on-error"
                          : "border border-outline text-outline"
                      }`}
                    >
                      {a.signal}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="p-unit-4 border-t border-surface-variant font-code-snippet text-code-snippet text-outline text-center">
          {filtered.length} ASSETS DISPLAYED
        </div>
      </div>
    </>
  );
}
