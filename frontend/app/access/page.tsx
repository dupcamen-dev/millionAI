"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AccessPage() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [status, setStatus] = useState("> INIT SECURE HANDSHAKE...");
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const timer = setTimeout(() => setStatus("> AWAITING INPUT..."), 500);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;

    setStatus("> VERIFYING ACCESS CODE...");

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Access-Code": code },
      });
      const data = await res.json();
      if (data.valid) {
        setStatus("> ACCESS GRANTED. REDIRECTING...");
        localStorage.setItem("MILLION_ACCESS_CODE", code);
        await new Promise((r) => setTimeout(r, 500));
        router.push("/admin");
      } else {
        throw new Error("invalid");
      }
    } catch {
      setError(true);
      setStatus("> AUTH FAILED: INVALID CREDENTIALS");
      setTimeout(() => {
        setCode("");
        setError(false);
        setStatus("> AWAITING INPUT...");
        inputRef.current?.focus();
      }, 1500);
    }
  };

  return (
    <div className="crt min-h-screen bg-black text-on-background font-body-lg flex items-center justify-center">
      <main className="w-full max-w-2xl px-margin-mobile md:px-margin-desktop z-10">
        <div className="border border-primary-fixed-dim bg-black p-unit-8 flex flex-col gap-unit-8">
          <div className="border-b border-outline-variant pb-unit-4 flex justify-between items-center">
            <span className="font-label-caps text-label-caps text-primary-fixed-dim">SYS_AUTH_NODE</span>
            <span className="font-code-snippet text-code-snippet text-on-surface-variant flex items-center gap-unit-2">
              <span className="text-primary-fixed-dim">&gt;</span>
              SECURE CONNECTION
            </span>
          </div>

          <div className="flex flex-col gap-unit-4 pt-unit-4">
            <p className="font-headline-md text-headline-md text-primary-fixed-dim uppercase">
              SECURITY PROTOCOL: ENTER UNIQUE ACCESS CODE
            </p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-unit-8 mt-unit-8">
              <div className="flex items-center border-b border-outline-variant focus-within:border-primary-fixed-dim pb-unit-2 transition-colors">
                <span className="font-headline-lg text-headline-lg text-primary-fixed-dim mr-unit-2">&gt;</span>
                <div className="relative flex-1">
                  <input
                    ref={inputRef}
                    type="password"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="w-full bg-transparent border-none text-primary-fixed-dim font-headline-lg text-headline-lg p-0 focus:ring-0 outline-none"
                    autoComplete="off"
                    maxLength={20}
                    style={{ color: "transparent" }}
                  />
                  <span className="absolute inset-0 pointer-events-none font-headline-lg text-headline-lg text-primary-fixed-dim tracking-[0.2em] flex items-center">
                    {"*".repeat(code.length)}
                  </span>
                </div>
                <span className="inline-block w-2 h-[1.2em] bg-primary-fixed-dim ml-1 cursor-blink" />
              </div>

              <div className="flex justify-end mt-unit-4">
                <button
                  type="submit"
                  className="bg-black border border-primary-fixed-dim text-primary-fixed-dim font-label-caps text-label-caps px-unit-8 py-unit-4 hover:bg-primary-fixed-dim hover:text-black transition-colors duration-100 flex items-center gap-unit-2 uppercase"
                >
                  [ EXECUTE ]
                  <span className="text-[16px]">&gt;</span>
                </button>
              </div>
            </form>
          </div>

          <div className="mt-unit-8 pt-unit-4 border-t border-outline-variant font-code-snippet text-code-snippet text-on-surface-variant opacity-50 flex flex-col gap-1">
            <p className={error ? "text-error" : ""}>{status}</p>
          </div>
        </div>
      </main>

      <footer className="fixed bottom-0 w-full flex justify-between items-center px-margin-mobile md:px-margin-desktop py-unit-2 z-50 border-t border-outline-variant bg-black">
        <span className="font-code-snippet text-code-snippet uppercase text-on-surface-variant" />
        <span className="font-label-caps text-label-caps text-primary-fixed-dim">MILLION</span>
      </footer>
    </div>
  );
}
