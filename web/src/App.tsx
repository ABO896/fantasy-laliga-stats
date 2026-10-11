import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import PlayerBrowser from "./pages/PlayerBrowser";

// The browser is the landing page and loads with the app; every other page
// (and Recharts with them) loads on first visit, keeping the first download
// small.
const PlayerDetail = lazy(() => import("./pages/PlayerDetail"));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const SquadPage = lazy(() => import("./pages/SquadPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const StatsPage = lazy(() => import("./pages/StatsPage"));
const ComparePage = lazy(() => import("./pages/ComparePage"));
const TransfersPage = lazy(() => import("./pages/TransfersPage"));

function page(element: React.ReactNode) {
  return <Suspense fallback={<p className="state-note">Loading…</p>}>{element}</Suspense>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<PlayerBrowser />} />
        <Route path="/players/:playerId" element={page(<PlayerDetail />)} />
        <Route path="/compare" element={page(<ComparePage />)} />
        <Route path="/stats" element={page(<StatsPage />)} />
        <Route path="/health" element={page(<HealthPage />)} />
        <Route path="/squad" element={page(<SquadPage />)} />
        <Route path="/transfers" element={page(<TransfersPage />)} />
        <Route path="/settings" element={page(<SettingsPage />)} />
      </Route>
    </Routes>
  );
}
