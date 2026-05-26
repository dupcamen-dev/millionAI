"use client";

import { useEffect, useState } from "react";
import { apiGet, StrategyData, SavedModel, ModelsListData } from "@/lib/api";

const NEURON_LABELS = ["N0","N1","N2","N3","N4","N5","N6","N7","N8","N9","N10","N11","N12","N13","N14","N15"];

function weightColor(w: number): string {
  const norm = (w + 0.3) / 0.6;
  const r = Math.round(255 * (1 - norm));
  const g = Math.round(255 * norm);
  const b = Math.round(50 + Math.abs(norm - 0.5) * 50);
  return `rgb(${r},${g},${b})`;
}

export default function StrategyPage() {
  const [weights, setWeights] = useState<number[][]>([]);
  const [strategy, setStrategy] = useState<StrategyData | null>(null);
  const [models, setModels] = useState<SavedModel[]>([]);
  const [selectedNeuron, setSelectedNeuron] = useState<number | null>(null);
  const [view, setView] = useState<"matrix" | "distribution">("matrix");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<StrategyData>("/api/v1/strategy").then((data) => {
      setStrategy(data);
      if (data.neurons?.length > 0) setWeights(data.neurons);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    apiGet<ModelsListData>("/api/v1/strategy/models").then((data) => {
      setModels(data.models || []);
    }).catch(() => {});
  }, []);

  const meanW = (arr: number[]) => arr.reduce((s, v) => s + v, 0) / arr.length;
  const buyWeights = weights.slice(0, 8).flat();
  const sellWeights = weights.slice(8, 16).flat();
  const buyMean = buyWeights.length ? meanW(buyWeights) : 0;
  const sellMean = sellWeights.length ? meanW(sellWeights) : 0;
  const allFlat = buyWeights.concat(sellWeights);
  const wMin = allFlat.length ? Math.min(...allFlat) : 0;
  const wMax = allFlat.length ? Math.max(...allFlat) : 0;
  const isLive = strategy?.live || false;

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">STRATEGY</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">
            {isLive ? (
              <>&gt; LIVE: {strategy?.symbol} {strategy?.leverage}x | {strategy?.neurons?.length || strategy?.neurons?.length || weights.length} NEURONS x 64 WEIGHTS | {strategy?.trades || 0}T {strategy?.wins || 0}W</>
            ) : weights.length > 0 ? (
              <>&gt; SAVED: {strategy?.symbol} {strategy?.leverage}x | {strategy?.neurons?.length || weights.length} NEURONS x 64 WEIGHTS</>
            ) : (
              "> NO MODEL DATA. START TRADER TO TRAIN."
            )}
          </p>
        </div>
        <div className="flex gap-unit-2 font-label-caps text-label-caps">
          <button
            onClick={() => setView("matrix")}
            className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
              view === "matrix" ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim" : "border-outline-variant text-outline hover:border-primary-fixed-dim"
            }`}
          >
            MATRIX
          </button>
          <button
            onClick={() => setView("distribution")}
            className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
              view === "distribution" ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim" : "border-outline-variant text-outline hover:border-primary-fixed-dim"
            }`}
          >
            DISTRIBUTION
          </button>
          {isLive && (
            <span className="px-unit-4 py-unit-2 border border-[#28a745] text-[#28a745] uppercase animate-pulse">
              LIVE
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-gutter">
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">SYMBOL</div>
          <div className="font-display text-display text-primary-fixed-dim mt-unit-2">
            {strategy?.symbol || "--"}
          </div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">LEVERAGE</div>
          <div className="font-display text-display text-primary-fixed-dim mt-unit-2">
            {strategy?.leverage || 1}x
          </div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">BUY MEAN</div>
          <div className="font-display text-display text-primary-fixed-dim mt-unit-2">{buyMean.toFixed(4)}</div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">SELL MEAN</div>
          <div className="font-display text-display text-error mt-unit-2">{sellMean.toFixed(4)}</div>
        </div>
      </div>

      {models.length > 0 && (
        <div className="border border-surface-variant bg-background">
          <div className="p-unit-4 border-b border-surface-variant bg-surface-container-low">
            <h2 className="font-label-caps text-label-caps text-on-surface uppercase">SAVED MODELS</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse font-code-snippet text-code-snippet">
              <thead>
                <tr className="border-b border-surface-variant text-outline">
                  <th className="p-unit-4 uppercase font-normal">SYMBOL</th>
                  <th className="p-unit-4 uppercase font-normal text-right">LEV</th>
                  <th className="p-unit-4 uppercase font-normal text-right">RISK</th>
                  <th className="p-unit-4 uppercase font-normal text-right">UPDATED</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => (
                  <tr key={i} className={`border-b border-surface-variant hover:bg-surface-container-low ${m.symbol === strategy?.symbol ? "bg-surface-container-lowest" : ""}`}>
                    <td className="p-unit-4">
                      <span className={m.symbol === strategy?.symbol ? "text-primary-fixed-dim" : ""}>
                        {m.symbol}
                      </span>
                    </td>
                    <td className="p-unit-4 text-right">{m.leverage}x</td>
                    <td className="p-unit-4 text-right" style={{ color: m.risk_score > 0 ? "#28a745" : "#ef4444" }}>
                      {m.risk_score.toFixed(2)}
                    </td>
                    <td className="p-unit-4 text-right text-outline">
                      {new Date(m.updated_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {weights.length > 0 && view === "matrix" && (
        <div className="border border-surface-variant bg-background overflow-x-auto">
          <div className="p-unit-4 border-b border-surface-variant bg-surface-container-low">
            <h2 className="font-label-caps text-label-caps text-on-surface uppercase">WEIGHT MATRIX (16 x 64)</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse font-code-snippet text-[11px]">
              <thead>
                <tr className="border-b border-surface-variant text-outline">
                  <th className="p-unit-2 uppercase sticky left-0 bg-background z-10" />
                  {Array.from({ length: 64 }, (_, i) => (
                    <th key={i} className="p-unit-1 text-right font-normal uppercase opacity-60">{i}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weights.map((row, ni) => (
                  <tr key={ni}
                    onClick={() => setSelectedNeuron(selectedNeuron === ni ? null : ni)}
                    className={`border-b border-surface-variant cursor-pointer transition-colors ${
                      selectedNeuron === ni ? "bg-surface-container-low" : "hover:bg-surface-container-lowest"
                    }`}
                  >
                    <td className={`p-unit-2 font-bold sticky left-0 bg-background z-10 ${ni < 8 ? "text-primary-fixed-dim" : "text-error"}`}>
                      {NEURON_LABELS[ni]}
                    </td>
                    {row.map((w, ki) => (
                      <td key={ki} className="p-unit-1 text-right" style={{ color: weightColor(w) }} title={`N${ni}[${ki}]=${w.toFixed(6)}`}>
                        {w.toFixed(3)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {weights.length > 0 && view === "distribution" && (
        <div className="border border-surface-variant bg-background p-unit-8">
          <h2 className="font-label-caps text-label-caps text-on-surface uppercase mb-unit-8">
            WEIGHT DISTRIBUTION [{wMin.toFixed(2)} : {wMax.toFixed(2)}]
          </h2>
          <div className="flex items-end gap-unit-1" style={{ height: 200 }}>
            {Array.from({ length: 40 }, (_, i) => {
              const binStart = wMin + (i / 40) * (wMax - wMin);
              const binEnd = binStart + (wMax - wMin) / 40;
              const buyCount = buyWeights.filter((w) => w >= binStart && w < binEnd).length;
              const sellCount = sellWeights.filter((w) => w >= binStart && w < binEnd).length;
              const maxCount = Math.max(60, buyCount, sellCount);
              const buyH = maxCount > 0 ? (buyCount / maxCount) * 180 : 1;
              const sellH = maxCount > 0 ? (sellCount / maxCount) * 180 : 1;
              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end gap-[1px] relative">
                  <div className="w-full bg-error opacity-70" style={{ height: `${Math.max(sellH, 1)}px` }} />
                  <div className="w-full bg-primary-fixed-dim opacity-70" style={{ height: `${Math.max(buyH, 1)}px` }} />
                  {i % 5 === 0 && (
                    <span className="font-code-snippet text-[9px] text-outline -rotate-45 mt-unit-2 whitespace-nowrap">
                      {((binStart + binEnd) / 2).toFixed(2)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-unit-8 flex gap-unit-8 justify-center font-code-snippet text-code-snippet">
            <span className="flex items-center gap-unit-2"><span className="w-4 h-3 bg-primary-fixed-dim" /> BUY</span>
            <span className="flex items-center gap-unit-2"><span className="w-4 h-3 bg-error" /> SELL</span>
          </div>
        </div>
      )}

      {loading && (
        <div className="font-code-snippet text-code-snippet text-outline p-unit-8 text-center">
          &gt; LOADING MODEL DATA...
        </div>
      )}
    </>
  );
}