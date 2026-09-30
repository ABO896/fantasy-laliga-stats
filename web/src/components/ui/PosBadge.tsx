/** A position (POR/DEF/MED/DEL) in its fixed colour — the same four colours
 * wherever a position appears. */
export default function PosBadge({ position }: { position: string }) {
  return (
    <span className="pos-badge" data-pos={position}>
      {position}
    </span>
  );
}
