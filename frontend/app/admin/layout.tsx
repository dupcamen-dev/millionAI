"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { getAccessCode } from "@/lib/api";

const SIDEBAR_ITEMS = [
  { label: "TERMINAL", href: "/admin" },
  { label: "ASSETS", href: "/admin/assets" },
  { label: "STRATEGY", href: "/admin/strategy" },
  { label: "LOGS", href: "/admin/logs" },
] as const;

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!getAccessCode()) {
      router.push("/access");
    } else {
      setAuthorized(true);
    }
  }, [router]);

  if (!authorized) return null;

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
            {SIDEBAR_ITEMS.map((item) => {
              const active = pathname === item.href;
              return active ? (
                <span
                  key={item.href}
                  className="bg-primary-fixed-dim text-on-primary flex items-center gap-unit-2 px-unit-4 py-unit-2 uppercase w-full"
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-primary-fixed-dim flex items-center gap-unit-2 px-unit-4 py-unit-2 hover:bg-surface-variant transition-colors uppercase w-full"
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>
        <main className="flex-1 overflow-y-auto p-margin-mobile md:p-margin-desktop bg-surface-container-lowest">
          <div className="max-w-7xl mx-auto space-y-unit-8">
            {children}
          </div>
        </main>
      </div>
      <Footer />
    </div>
  );
}
