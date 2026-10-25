"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Race", match: (p: string) => p === "/" },
  { href: "/results", label: "Results", match: (p: string) => p.startsWith("/results") },
  { href: "/models", label: "Models", match: (p: string) => p.startsWith("/models") },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav className="relative z-10 border-b border-white/10 bg-ink-900/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 md:px-8">
        <Link href="/" className="group flex items-center gap-3">
          <span
            className="flex h-9 w-9 items-center justify-center bg-accent font-display text-sm tracking-widest text-white transition-transform group-hover:-skew-x-6"
            aria-hidden
          >
            RF
          </span>
          <span className="flex flex-col leading-none">
            <span className="font-display text-xl tracking-[0.12em] text-white">
              RaceForesight
            </span>
            <span className="mt-1 text-[9px] uppercase tracking-[0.28em] text-muted">
              lap · order · pace
            </span>
          </span>
        </Link>
        <div className="flex items-center gap-0.5">
          {LINKS.map((link) => {
            const active = link.match(pathname);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`relative px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                  active ? "text-white" : "text-muted hover:text-white"
                }`}
              >
                {link.label}
                {active && (
                  <span
                    className="absolute inset-x-1 -bottom-0.5 h-[2px] bg-accent"
                    style={{ clipPath: "polygon(0 0, 100% 0, 92% 100%, 0 100%)" }}
                    aria-hidden
                  />
                )}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
