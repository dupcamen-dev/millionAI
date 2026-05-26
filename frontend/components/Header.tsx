"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "INDEX", href: "/" },
  { label: "ACCESS", href: "/access" },
  { label: "ADMIN", href: "/admin" },
  { label: "API", href: "/settings/api" },
] as const;

export default function Header() {
  const pathname = usePathname();

  return (
    <header className="bg-background border-b border-outline-variant flex justify-between items-center w-full px-margin-mobile md:px-margin-desktop h-16 shrink-0 z-50">
      <Link href="/" className="font-headline-md text-headline-md font-bold text-primary-fixed-dim uppercase tracking-tight">
        MILLION
      </Link>
      <nav className="hidden md:flex gap-unit-4 font-label-caps text-label-caps">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return active ? (
            <span key={item.href} className="bg-primary-fixed-dim text-on-primary px-unit-2 py-unit-1 opacity-90 uppercase cursor-default">
              {item.label}
            </span>
          ) : (
            <Link
              key={item.href}
              href={item.href}
              className="text-primary-fixed-dim hover:bg-primary-fixed-dim hover:text-on-primary px-unit-2 py-unit-1 transition-colors duration-100 uppercase"
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
