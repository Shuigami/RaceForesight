type Props = {
  title: string;
  children: React.ReactNode;
};

export function ExplainPanel({ title, children }: Props) {
  return (
    <aside className="border-l-2 border-accent/70 bg-ink-850/50 py-4 pl-5 pr-4">
      <h3 className="mb-3 text-[11px] uppercase tracking-[0.18em] text-accent">{title}</h3>
      <div className="space-y-2 text-sm leading-relaxed text-fog">{children}</div>
    </aside>
  );
}
