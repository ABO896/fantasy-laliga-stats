import type { ReactNode } from "react";

interface EmptyStateProps {
  heading: string;
  body: string;
  action?: ReactNode;
}

export default function EmptyState({ heading, body, action }: EmptyStateProps) {
  return (
    <section className="flex flex-col items-center gap-sm px-md py-3xl text-center">
      <svg
        aria-hidden="true"
        viewBox="0 0 48 32"
        className="mb-xs h-8 w-12 text-[color:var(--color-line)]"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <rect x="1" y="1" width="46" height="30" rx="2" />
        <line x1="24" y1="1" x2="24" y2="31" />
        <circle cx="24" cy="16" r="6" />
      </svg>
      <h2 className="section-title">{heading}</h2>
      <p className="max-w-[28rem] text-sm muted">{body}</p>
      {action && <div className="pt-sm">{action}</div>}
    </section>
  );
}
