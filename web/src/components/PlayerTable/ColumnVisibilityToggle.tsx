import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Table } from "@tanstack/react-table";
import type { features } from "./columns";
import type { PlayerRow } from "../../api-client/players";

interface ColumnVisibilityToggleProps {
  table: Table<typeof features, PlayerRow>;
  /** The column id the price filter's basis selector is currently forcing
   * visible (see PlayerTable's `revealColumn`). Its checkbox is disabled
   * here rather than left clickable-but-inert — unchecking it would have no
   * effect, since `effectiveVisibility` re-forces the column visible on the
   * very next render. */
  forcedVisibleColumn?: string;
}

/** Chevron-triggered control listing every column with a checkbox bound to
 * the table's column-visibility state — the D-06 hidden columns are one
 * click away. The trigger's icon is 16-20px but its click target is padded
 * out to the UI-SPEC's 44px minimum (h-11 w-11 = 44px). */
export default function ColumnVisibilityToggle({
  table,
  forcedVisibleColumn,
}: ColumnVisibilityToggleProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label="Toggle column visibility"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="btn btn-secondary h-9 px-sm"
      >
        <span className="text-sm font-semibold">Columns</span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-xs w-56 rounded-[var(--radius-md)] border border-line bg-surface p-sm shadow-[var(--shadow-pop)]">
          {table.getAllLeafColumns().map((column) => {
            const isForcedVisible = column.id === forcedVisibleColumn;
            return (
              <label key={column.id} className="flex items-center gap-xs py-xs text-sm">
                <input
                  type="checkbox"
                  checked={column.getIsVisible()}
                  disabled={isForcedVisible}
                  title={
                    isForcedVisible
                      ? "Shown because it's the price filter's active basis — change the basis to hide it"
                      : undefined
                  }
                  onChange={column.getToggleVisibilityHandler()}
                />
                {typeof column.columnDef.header === "string"
                  ? column.columnDef.header
                  : column.id}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
