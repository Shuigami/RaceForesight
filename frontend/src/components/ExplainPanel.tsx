type Props = {
  title: string;
  children: React.ReactNode;
};

export function ExplainPanel({ title, children }: Props) {
  return (
    <aside className="border border-white/10 bg-ink-850/70 p-5 backdrop-blur">
      <h3 className="mb-3 text-[11px] uppercase tracking-[0.18em] text-accent">{title}</h3>
      <div className="space-y-2 text-sm leading-relaxed text-fog">{children}</div>
    </aside>
  );
}
