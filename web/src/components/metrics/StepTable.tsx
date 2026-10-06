import type { ReactNode } from "react";

/** A metric's calculation, collapsed by default behind a `<details>` so
 * the player page stays scannable — step · value · meaning, with the
 * headline number always last and bold. */
export interface Step {
  step: string;
  value: ReactNode;
  meaning: string;
}

export default function StepTable({
  steps,
  headline,
}: {
  steps: Step[];
  headline: Step;
}) {
  return (
    <details>
      <summary>How it's calculated</summary>
      <table className="data-table compact">
        <thead>
          <tr>
            <th>Step</th>
            <th>Value</th>
            <th>Meaning</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((s) => (
            <tr key={s.step}>
              <td>{s.step}</td>
              <td className="num tabular">{s.value}</td>
              <td className="muted">{s.meaning}</td>
            </tr>
          ))}
          <tr>
            <td>
              <strong>{headline.step}</strong>
            </td>
            <td className="num tabular">
              <strong>{headline.value}</strong>
            </td>
            <td className="muted">
              <strong>{headline.meaning}</strong>
            </td>
          </tr>
        </tbody>
      </table>
    </details>
  );
}
