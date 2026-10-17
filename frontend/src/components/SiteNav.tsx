"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Strategy" },
  { href: "/classification", label: "Classification" },
  { href: "/models", label: "Models" },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav className="relative z-10 border-b border-white/10 bg-ink-900/70 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 md:px-8">
        <Link href="/" className="font-display text-2xl tracking-[0.08em] text-white">
          RaceForesight
        </Link>
        <div className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                  active ? "text-accent" : "text-muted hover:text-white"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
