import type { ReactNode } from "react";

/** Typeset maths without a library — a handful of small, composable
 * pieces (a stacked fraction, a superscript, a multiplication sign) that
 * metric step tables and formula callouts build from, so a metric card
 * never prints a raw formula string like `^`, `e^`, `*` or `sqrt(`. */

/** A stacked fraction: numerator above a top-bordered denominator. */
export function Frac({ num, den }: { num: ReactNode; den: ReactNode }) {
  return (
    <span className="frac">
      <span className="frac-num">{num}</span>
      <span className="frac-den">{den}</span>
    </span>
  );
}

/** A superscript, for exponents. */
export function Sup({ children }: { children: ReactNode }) {
  return <sup>{children}</sup>;
}

/** A multiplication sign padded with thin spaces, so it doesn't crowd its
 * operands the way a bare "x" or "*" would. */
export function Times() {
  return <>{" × "}</>;
}

/** Wraps a formula's pieces in an accessible, labelled math span. */
export function Formula({ children, label }: { children: ReactNode; label: string }) {
  return (
    <span role="math" aria-label={label} className="formula">
      {children}
    </span>
  );
}
