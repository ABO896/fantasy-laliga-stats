import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import PlayerBrowser from "./pages/PlayerBrowser";
import PlayerDetail from "./pages/PlayerDetail";
import HealthPage from "./pages/HealthPage";
import SquadPage from "./pages/SquadPage";
import SettingsPage from "./pages/SettingsPage";
import StatsPage from "./pages/StatsPage";
import ComparePage from "./pages/ComparePage";
import TransfersPage from "./pages/TransfersPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<PlayerBrowser />} />
        <Route path="/players/:playerId" element={<PlayerDetail />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/squad" element={<SquadPage />} />
        <Route path="/transfers" element={<TransfersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
