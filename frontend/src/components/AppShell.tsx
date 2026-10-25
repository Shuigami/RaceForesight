import { SiteNav } from "./SiteNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-x-clip bg-background">
      <div className="pointer-events-none absolute inset-0 bg-timing" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "repeating-conic-gradient(#fff 0% 25%, transparent 0% 50%)",
          backgroundSize: "18px 18px",
          maskImage:
            "linear-gradient(115deg, transparent 35%, black 55%, black 75%, transparent 95%)",
          WebkitMaskImage:
            "linear-gradient(115deg, transparent 35%, black 55%, black 75%, transparent 95%)",
        }}
        aria-hidden
      />
      <SiteNav />
      {children}
    </div>
  );
}
