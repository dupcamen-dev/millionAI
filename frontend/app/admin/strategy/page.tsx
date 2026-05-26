"use client";

import { useState } from "react";

const NEURON_LABELS = ["N0", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10", "N11", "N12", "N13", "N14", "N15"];
const KERNEL_LABELS = Array.from({ length: 64 }, (_, i) => `K${i}`);

function generateWeights(): number[][] {
  const neurons = 16;
  const kernels = 64;
  const w: number[][] = [];
  for (let n = 0; n < neurons; n++) {
    const row: number[] = [];
    const pop = n < 8 ? 1 : -1;
    for (let k = 0; k < kernels; k++) {
      const base = pop * (Math.random() * 0.1 + 0.02);
      const noise = (Math.random() - 0.5) * 0.08;
      row.push(Math.max(-0.238, Math.min(0.228, base + noise)));
    }
    w.push(row);
  }
  return w;
}

const WEIGHTS = generateWeights();

function weightColor(w: number): string {
  const norm = (w + 0.238) / (0.238 + 0.228);
  const r = Math.round(255 * (1 - norm));
  const g = Math.round(255 * norm);
  return `rgb(${r}, ${g}, 50)`;
}

export default function StrategyPage() {
  const [selectedNeuron, setSelectedNeuron] = useState<number | null>(null);
  const [view, setView] = useState<"matrix" | "distribution">("matrix");

  const meanW = (arr: number[]) => arr.reduce((s, v) => s + v, 0) / arr.length;
  const buyWeights = WEIGHTS.slice(0, 8).flat();
  const sellWeights = WEIGHTS.slice(8, 16).flat();
  const buyMean = meanW(buyWeights);
  const sellMean = meanW(sellWeights);

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">STRATEGY</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; SNN.CONFIG: 16 NEURONS × 64 WEIGHTS</p>
        </div>
        <div className="flex gap-unit-2 font-label-caps text-label-caps">
          <button
            onClick={() => setView("matrix")}
            className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
              view === "matrix"
                ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
                : "border-outline-variant text-outline hover:border-primary-fixed-dim"
            }`}
          >
            MATRIX
          </button>
          <button
            onClick={() => setView("distribution")}
            className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
              view === "distribution"
                ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
                : "border-outline-variant text-outline hover:border-primary-fixed-dim"
            }`}
          >
            DISTRIBUTION
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">BUY POPULATION</div>
          <div className="font-display text-display text-primary-fixed-dim mt-unit-2">8</div>
          <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-1">
            Mean: {buyMean.toFixed(4)}
          </div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">SELL POPULATION</div>
          <div className="font-display text-display text-error mt-unit-2">8</div>
          <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-1">
            Mean: {sellMean.toFixed(4)}
          </div>
        </div>
        <div className="border border-surface-variant p-unit-4 bg-background">
          <div className="font-label-caps text-label-caps text-outline uppercase">TOTAL WEIGHTS</div>
          <div className="font-display text-display text-primary-fixed-dim mt-unit-2">1024</div>
          <div className="font-code-snippet text-code-snippet text-on-surface-variant mt-unit-1">
            Range: [-0.238, +0.228]
          </div>
        </div>
      </div>

      {view === "matrix" ? (
        <div className="border border-surface-variant bg-background overflow-x-auto">
          <div className="p-unit-4 border-b border-surface-variant bg-surface-container-low">
            <h2 className="font-label-caps text-label-caps text-on-surface uppercase">WEIGHT MATRIX</h2>
          </div>
          <div className="overflow-x-auto" style={{ minHeight: 200 }}>
            <table className="w-full text-left border-collapse font-code-snippet text-[11px]">
              <thead>
                <tr className="border-b border-surface-variant text-outline">
                  <th className="p-unit-2 uppercase sticky left-0 bg-surface-container-lowest z-10" />
                  {KERNEL_LABELS.map((k) => (
                    <th key={k} className="p-unit-1 text-right font-normal uppercase">{k}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {WEIGHTS.map((row, ni) => (
                  <tr
                    key={ni}
                    onClick={() => setSelectedNeuron(selectedNeuron === ni ? null : ni)}
                    className={`border-b border-surface-variant cursor-pointer transition-colors ${
                      selectedNeuron === ni ? "bg-surface-container-low" : "hover:bg-surface-container-lowest"
                    }`}
                  >
                    <td className={`p-unit-2 font-bold sticky left-0 z-10 ${
                      ni < 8 ? "text-primary-fixed-dim" : "text-error"
                    }`}>
                      {NEURON_LABELS[ni]}
                    </td>
                    {row.map((w, ki) => (
                      <td
                        key={ki}
                        className="p-unit-1 text-right"
                        style={{ color: weightColor(w) }}
                        title={`N${ni} K${ki}: ${w.toFixed(4)}`}
                      >
                        {w.toFixed(3)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="border border-surface-variant bg-background p-unit-8">
          <h2 className="font-label-caps text-label-caps text-on-surface uppercase mb-unit-8">WEIGHT DISTRIBUTION</h2>
          <div className="flex items-end gap-unit-1" style={{ height: 200 }}>
            {Array.from({ length: 40 }, (_, i) => {
              const binStart = -0.238 + (i / 40) * (0.228 + 0.238);
              const binEnd = binStart + (0.228 + 0.238) / 40;
              const binMid = (binStart + binEnd) / 2;
              const buyCount = buyWeights.filter((w) => w >= binStart && w < binEnd).length;
              const sellCount = sellWeights.filter((w) => w >= binStart && w < binEnd).length;
              const maxCount = 60;
              const buyH = (buyCount / maxCount) * 180;
              const sellH = (sellCount / maxCount) * 180;
              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end gap-[1px] relative">
                  <div
                    className="w-full bg-error opacity-70"
                    style={{ height: `${Math.max(sellH, 1)}px` }}
                  />
                  <div
                    className="w-full bg-primary-fixed-dim opacity-70"
                    style={{ height: `${Math.max(buyH, 1)}px` }}
                  />
                  {i % 5 === 0 && (
                    <span className="font-code-snippet text-[9px] text-outline -rotate-45 mt-unit-2 whitespace-nowrap">
                      {binMid.toFixed(2)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-unit-8 flex gap-unit-8 justify-center font-code-snippet text-code-snippet">
            <span className="flex items-center gap-unit-2">
              <span className="w-4 h-3 bg-primary-fixed-dim" /> BUY
            </span>
            <span className="flex items-center gap-unit-2">
              <span className="w-4 h-3 bg-error" /> SELL
            </span>
          </div>
        </div>
      )}
    </>
  );
}
