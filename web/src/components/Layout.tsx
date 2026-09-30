import { Link, NavLink, Outlet } from "react-router-dom";
import StaleBanner from "./StaleBanner";
import SquadBar from "./SquadBar";

const NAV = [
  { to: "/", label: "Player Browser", end: true },
  { to: "/compare", label: "Compare" },
  { to: "/stats", label: "League Stats" },
  { to: "/squad", label: "My Squad" },
  { to: "/transfers", label: "Transfers" },
  { to: "/health", label: "Scrape Health" },
  { to: "/settings", label: "Settings" },
];

// The active tab carries a yellow-card marker along its bottom edge — the
// one place the decorative accent appears besides the watchlist star.
const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `relative flex h-full items-center whitespace-nowrap px-sm font-[family-name:var(--font-display)] text-[16px] font-semibold tracking-[0.01em] transition-colors after:absolute after:inset-x-sm after:bottom-0 after:h-[3px] after:rounded-t-sm ${
    isActive
      ? "text-[color:var(--color-board-ink)] after:bg-[color:var(--color-card)]"
      : "text-[color:var(--color-board-muted)] hover:text-[color:var(--color-board-ink)] after:bg-transparent"
  }`;

function CentreSpot() {
  return (
    <svg aria-hidden="true" viewBox="0 0 28 28" className="h-7 w-7 shrink-0">
      <rect x="1" y="1" width="26" height="26" rx="5" fill="var(--color-pitch)" />
      <line x1="14" y1="1" x2="14" y2="27" stroke="var(--color-pitch-line)" strokeWidth="1.5" />
      <circle cx="14" cy="14" r="6" fill="none" stroke="var(--color-pitch-line)" strokeWidth="1.5" />
      <circle cx="14" cy="14" r="1.8" fill="var(--color-card)" />
    </svg>
  );
}

export default function Layout() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 bg-[color:var(--color-board)] shadow-[0_1px_0_rgb(0_0_0/0.25)]">
        <div className="mx-auto flex max-w-[1600px] flex-col lg:h-14 lg:flex-row lg:items-stretch lg:gap-xl lg:px-xl">
          <Link
            to="/"
            className="flex items-center gap-sm px-md pt-sm text-[color:var(--color-board-ink)] lg:px-0 lg:pt-0"
          >
            <CentreSpot />
            <span className="font-[family-name:var(--font-display)] text-[21px] font-bold leading-none tracking-[0.01em]">
              Fantasy LaLiga Stats
            </span>
          </Link>
          {/* Its own horizontal scroller on narrow screens, so seven tabs
              never push the page sideways (UI-02). */}
          <nav aria-label="Main" className="h-11 overflow-x-auto px-xs lg:h-auto lg:px-0">
            <ul className="flex h-full items-stretch">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.end} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <StaleBanner />
      <SquadBar />
      <main className="mx-auto max-w-[1600px] px-md py-lg sm:px-lg lg:px-xl lg:py-xl">
        <Outlet />
      </main>
    </div>
  );
}
