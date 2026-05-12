import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import MatchmakingPage from './pages/MatchmakingPage'
import LobbyPage from './pages/LobbyPage'
import GamePage from './pages/GamePage'
import LeaderboardPage from './pages/LeaderboardPage'
import MatchFoundPage from './pages/MatchFoundPage'
import Layout from './components/Layout'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="matchmaking" element={<MatchmakingPage />} />
        <Route path="match-found" element={<MatchFoundPage />} />
        <Route path="lobby" element={<LobbyPage />} />
        <Route path="game" element={<GamePage />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
