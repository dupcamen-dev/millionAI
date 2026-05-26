"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

export default function ApiConfigPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem("MILLION_ACCESS_CODE");
    if (stored !== "1231") {
      router.push("/access");
    } else {
      setAuthorized(true);
    }
  }, [router]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey || !apiSecret) return;
    localStorage.setItem("MILLION_API_KEY", apiKey);
    localStorage.setItem("MILLION_API_SECRET", apiSecret);
    localStorage.setItem("MILLION_TELEGRAM_BOT_TOKEN", telegramToken);
    localStorage.setItem("MILLION_TELEGRAM_CHAT_ID", telegramChatId);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (!authorized) return null;

  return (
    <div className="min-h-screen bg-background text-on-surface font-body-lg flex flex-col">
      <Header />

      <main className="flex-1 flex items-start justify-center px-margin-mobile md:px-margin-desktop py-unit-8">
        <div className="w-full max-w-2xl">
          <div className="border border-outline-variant bg-background">
            <div className="p-unit-4 border-b border-outline-variant bg-surface-container-low">
              <h1 className="font-headline-md text-headline-md text-primary-fixed-dim uppercase">API_CONFIGURATION</h1>
              <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; BINANCE_FUTURES.KEYS</p>
            </div>

            <form onSubmit={handleSave} className="p-unit-8 flex flex-col gap-unit-8">
              <div className="flex flex-col gap-unit-4">
                <label className="font-label-caps text-label-caps text-outline uppercase">API_KEY</label>
                <input
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full"
                  placeholder="Enter your Binance API key..."
                  type="text"
                />
              </div>

              <div className="flex flex-col gap-unit-4">
                <label className="font-label-caps text-label-caps text-outline uppercase">API_SECRET</label>
                <input
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full"
                  placeholder="Enter your Binance API secret..."
                  type="password"
                />
              </div>

              <div className="border-t border-outline-variant my-unit-4" />

              <h2 className="font-label-caps text-label-caps text-primary-fixed-dim uppercase mb-unit-2">TELEGRAM_BOT</h2>

              <div className="flex flex-col gap-unit-4">
                <label className="font-label-caps text-label-caps text-outline uppercase">BOT_TOKEN</label>
                <input
                  value={telegramToken}
                  onChange={(e) => setTelegramToken(e.target.value)}
                  className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full"
                  placeholder="Enter your Telegram bot token..."
                  type="password"
                />
              </div>

              <div className="flex flex-col gap-unit-4">
                <label className="font-label-caps text-label-caps text-outline uppercase">CHAT_ID</label>
                <input
                  value={telegramChatId}
                  onChange={(e) => setTelegramChatId(e.target.value)}
                  className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full"
                  placeholder="Enter your Telegram chat ID..."
                  type="text"
                />
              </div>

              <div className="flex justify-between items-center mt-unit-4">
                <div className="font-code-snippet text-code-snippet text-on-surface-variant">
                  {saved ? (
                    <span className="text-primary-fixed-dim">&gt; KEYS_SAVED_SECURELY</span>
                  ) : (
                    <span>&gt; AWAITING_CONFIGURATION</span>
                  )}
                </div>
                <div className="flex gap-unit-4">
                  <button
                    type="submit"
                    className="bg-primary-fixed-dim text-on-primary font-label-caps text-label-caps px-unit-8 py-unit-4 hover:bg-background hover:text-primary-fixed-dim border border-primary-fixed-dim transition-colors duration-100 uppercase tracking-widest"
                  >
                    [ SAVE_KEYS ]
                  </button>
                </div>
              </div>
            </form>
          </div>

          <div className="mt-unit-8 border border-outline-variant bg-background p-unit-4">
            <h2 className="font-label-caps text-label-caps text-primary-fixed-dim uppercase mb-unit-4">INSTRUCTIONS</h2>
            <ol className="font-code-snippet text-code-snippet text-on-surface-variant flex flex-col gap-unit-2 list-decimal list-inside">
              <li>Go to Binance Futures API Management</li>
              <li>Create a new API key with futures trading permissions</li>
              <li>Copy the API Key and Secret Key</li>
              <li>Paste them above and save</li>
              <li>Keys are stored locally and never sent to our servers</li>
            </ol>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
