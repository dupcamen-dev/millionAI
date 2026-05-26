"use client";

import { useEffect, useState } from "react";
import { apiGet, ScreenerAsset } from "@/lib/api";

const FILTERS = ["ALL", "BUY", "SELL", "NEUTRAL"];

export default function AssetsPage() {
  const [assets, setAssets] = useState<ScreenerAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const data = await apiGet<{ assets: ScreenerAsset[] }>("/api/v1/assets/screener");
        setAssets(data.assets);
      } catch {
        console.error("Screener failed");
      }
      setLoading(false);
    };
    load();
  }, []);

  const getSignal = (a: ScreenerAsset): string => {
    if (a.score > 10) return "BUY";
    if (a.score < 5) return "SELL";
    return "NEUTRAL";
  };

  const filtered = assets.filter((a) => {
    const sig = getSignal(a);
    if (filter !== "ALL" && sig !== filter) return false;
    if (search && !a.symbol.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">ASSETS</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">
            &gt; SCREENER.ACTIVE: {assets.length} ASSETS
          </p>
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
                <th className="p-unit-4 uppercase font-normal text-right">SCORE</th>
                <th className="p-unit-4 uppercase font-normal text-center">SIGNAL</th>
              </tr>
            </thead>
            <tbody className="font-code-snippet text-code-snippet text-on-surface">
              {loading ? (
                <tr><td colSpan={6} className="p-unit-8 text-center text-outline">&gt; SCANNING BINANCE...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} className="p-unit-8 text-center text-outline">&gt; NO ASSETS MATCH FILTER</td></tr>
              ) : (
                filtered.map((a) => {
                  const sig = getSignal(a);
                  return (
                    <tr key={a.symbol} className="border-b border-surface-variant hover:bg-surface-container-low transition-colors group">
                      <td className="p-unit-4 font-bold text-primary-fixed-dim">{a.symbol}</td>
                      <td className="p-unit-4 text-right">${a.price.toFixed(4)}</td>
                      <td className="p-unit-4 text-right text-on-surface-variant">
                        ${(a.volume / 1_000_000).toFixed(0)}M
                      </td>
                      <td className="p-unit-4 text-right">{a.volatility.toFixed(2)}%</td>
                      <td className="p-unit-4 text-right">{a.score.toFixed(2)}</td>
                      <td className="p-unit-4 text-center">
                        <span
                          className={`px-unit-2 py-unit-1 uppercase text-[11px] tracking-widest ${
                            sig === "BUY"
                              ? "bg-primary-fixed-dim text-on-primary"
                              : sig === "SELL"
                              ? "bg-error text-on-error"
                              : "border border-outline text-outline"
                          }`}
                        >
                          {sig}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
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
