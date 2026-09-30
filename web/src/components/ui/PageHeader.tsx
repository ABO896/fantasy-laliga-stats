import type { ReactNode } from "react";

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Pages that already rendered an h2 title keep that level. */
  as?: "h1" | "h2";
}

/** The one page header every surface uses: a condensed title, an optional
 * one-line explanation, and actions pinned to the right on wide screens. */
export default function PageHeader({ title, subtitle, actions, as = "h1" }: PageHeaderProps) {
  const Heading = as;
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-lg gap-y-sm border-b border-line pb-md">
      <div className="min-w-0 max-w-[64rem]">
        <Heading className="page-title">{title}</Heading>
        {subtitle && <div className="pt-xs text-sm muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-sm">{actions}</div>}
    </header>
  );
}
