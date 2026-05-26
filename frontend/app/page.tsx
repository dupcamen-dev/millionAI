"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

export default function LandingPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [logs, setLogs] = useState<string[]>([
    "> SYS_INIT: KERNEL_LOADED",
    "> MEM_ALLOC: 4096 TB SECURE",
    "> AWAITING_CONNECTION...",
  ]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w: number, h: number;
    const dots: { x: number; y: number; baseAlpha: number; alpha: number; phase: number; speed: number }[] = [];
    const spacing = 32;

    function resize() {
      w = canvas!.width = window.innerWidth;
      h = canvas!.height = window.innerHeight;
      dots.length = 0;
      const cols = Math.floor(w / spacing) + 1;
      const rows = Math.floor(h / spacing) + 1;
      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          if (Math.random() > 0.6) {
            dots.push({
              x: i * spacing,
              y: j * spacing,
              baseAlpha: Math.random() * 0.5 + 0.1,
              alpha: 0,
              phase: Math.random() * Math.PI * 2,
              speed: Math.random() * 0.02 + 0.005,
            });
          }
        }
      }
    }

    function animate() {
      ctx!.clearRect(0, 0, w, h);
      dots.forEach((dot) => {
        dot.phase += dot.speed;
        dot.alpha = dot.baseAlpha + Math.sin(dot.phase) * 0.2;
        if (dot.alpha < 0) dot.alpha = 0;
        ctx!.fillStyle = `rgba(0, 230, 57, ${dot.alpha})`;
        ctx!.fillRect(dot.x - 1, dot.y - 1, 2, 2);
      });
      requestAnimationFrame(animate);
    }

    window.addEventListener("resize", resize);
    resize();
    animate();

    const logMessages = [
      "> SYNCING_NODES... [OK]",
      "> HFT_PROTOCOL_ACTIVE",
      "> LATENCY: 0.02ms",
      "> NEURAL_NET_TRAINING_CYCLE: 9942",
      "> ROUTING_ORDERS...",
      "> ENCRYPTION_KEY_ROTATED",
      "> AWAITING_CONNECTION...",
    ];
    let idx = 0;
    const interval = setInterval(() => {
      setLogs((prev) => [...prev.slice(-2), logMessages[idx % logMessages.length]]);
      idx++;
    }, 2000);

    return () => {
      window.removeEventListener("resize", resize);
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="relative min-h-screen flex flex-col bg-background">
      <canvas ref={canvasRef} id="bg-canvas" className="absolute inset-0 z-0 opacity-40 pointer-events-none" />

      <nav className="border-b border-outline-variant bg-background z-50">
        <div className="flex justify-between items-center w-full px-margin-mobile md:px-margin-desktop h-16">
          <div className="font-headline-md text-headline-md font-bold text-primary-fixed-dim tracking-tight uppercase">
            MILLION
          </div>
          <div className="hidden md:flex items-center gap-unit-8 font-label-caps text-label-caps">
            <span className="bg-primary-fixed-dim text-on-primary px-unit-2 py-unit-1 opacity-90 cursor-default">
              INDEX
            </span>
            <Link href="/auth" className="text-primary-fixed-dim hover:text-primary hover:bg-primary-fixed-dim hover:text-on-primary px-unit-2 py-unit-1 transition-colors duration-100">
              ACCESS
            </Link>
            <Link href="/dashboard" className="text-primary-fixed-dim hover:text-primary hover:bg-primary-fixed-dim hover:text-on-primary px-unit-2 py-unit-1 transition-colors duration-100">
              ADMIN
            </Link>
            <Link href="/settings/api" className="text-primary-fixed-dim hover:text-primary hover:bg-primary-fixed-dim hover:text-on-primary px-unit-2 py-unit-1 transition-colors duration-100">
              API
            </Link>
          </div>
          <div className="flex items-center">
            <span className="material-symbols-outlined text-primary-fixed-dim">terminal</span>
          </div>
        </div>
      </nav>

      <main className="flex-grow flex flex-col justify-center items-center px-margin-mobile md:px-margin-desktop relative z-10 w-full max-w-7xl mx-auto my-auto">
        <div className="border border-outline-variant bg-background p-unit-8 md:p-[64px] flex flex-col items-center justify-center max-w-4xl text-center relative overflow-hidden">
          <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary-fixed-dim" />
          <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary-fixed-dim" />
          <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary-fixed-dim" />
          <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary-fixed-dim" />

          <div className="mb-unit-8">
            <span className="material-symbols-outlined text-primary-fixed-dim" style={{ fontSize: "64px" }}>
              memory
            </span>
          </div>

          <h1 className="font-display text-display text-primary-fixed-dim uppercase leading-tight mb-unit-4">
            MILLION: THE NEXT GENERATION AI TRADING ENGINE
            <span className="inline-block w-[0.6em] h-[1em] bg-primary-fixed-dim align-text-bottom ml-2 cursor-blink" />
          </h1>

          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mt-unit-4 mb-unit-8">
            Written in a unique proprietary language for absolute efficiency.
          </p>

          <Link
            href="/auth"
            className="font-label-caps text-label-caps bg-primary-fixed-dim text-on-primary px-8 py-4 border border-primary-fixed-dim hover:bg-background hover:text-primary-fixed-dim transition-colors duration-100 uppercase tracking-widest flex items-center gap-unit-2 group"
          >
            <span className="material-symbols-outlined text-[16px]">key</span>
            [ ACCESS_SYSTEM ]
          </Link>

          <div className="mt-unit-8 w-full max-w-lg text-left border-t border-outline-variant pt-unit-4 font-code-snippet text-code-snippet text-on-surface-variant opacity-70">
            <div className="h-16 overflow-hidden flex flex-col justify-end">
              {logs.map((log, i) => (
                <div key={i}>{log}</div>
              ))}
            </div>
          </div>
        </div>
      </main>

      <footer className="fixed bottom-0 w-full flex justify-between items-center px-margin-mobile md:px-margin-desktop py-unit-2 z-50 bg-background border-t border-outline-variant">
        <div className="font-label-caps text-label-caps text-primary-fixed-dim tracking-widest uppercase">
          MILLION
        </div>
        <div className="font-code-snippet text-code-snippet uppercase text-primary-fixed-dim hidden md:block">
          AI: ONLINE // MARKET: LIVE // SYS_REF: 0x71C
        </div>
        <div className="flex gap-unit-4 font-code-snippet text-code-snippet uppercase">
          <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_01</span>
          <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_02</span>
          <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_03</span>
        </div>
      </footer>
    </div>
  );
}
