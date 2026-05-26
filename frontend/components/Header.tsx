"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getAccessCode } from "@/lib/api";

export default function Header() {
  const pathname = usePathname();
  const authorized = getAccessCode() === "1231";

  return (
    <header className="bg-background border-b border-outline-variant flex justify-between items-center w-full px-margin-mobile md:px-margin-desktop h-16 shrink-0 z-50">
      <Link href="/" className="font-headline-md text-headline-md font-bold text-primary-fixed-dim uppercase tracking-tight">
        MILLION
      </Link>
      <nav className="hidden md:flex gap-unit-4 font-label-caps text-label-caps">
        <HeaderLink href="/" label="INDEX" pathname={pathname} />
        <HeaderLink href="/access" label="ACCESS" pathname={pathname} />
        {authorized && <HeaderLink href="/admin" label="ADMIN" pathname={pathname} />}
        {authorized && <HeaderLink href="/settings/api" label="API" pathname={pathname} />}
      </nav>
    </header>
  );
}

function HeaderLink({ href, label, pathname }: { href: string; label: string; pathname: string }) {
  const active = pathname === href;
  return active ? (
    <span className="bg-primary-fixed-dim text-on-primary px-unit-2 py-unit-1 opacity-90 uppercase cursor-default">
      {label}
    </span>
  ) : (
    <Link
      href={href}
      className="text-primary-fixed-dim hover:bg-primary-fixed-dim hover:text-on-primary px-unit-2 py-unit-1 transition-colors duration-100 uppercase"
    >
      {label}
    </Link>
  );
}