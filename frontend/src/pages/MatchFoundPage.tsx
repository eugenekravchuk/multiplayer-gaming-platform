import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Swords, Users } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { useWebSocket } from '../hooks/useWebSocket'

export default function MatchFoundPage() {
  const { currentMatch, setCurrentLobby } = useGameStore()
  const { send } = useWebSocket()
  const navigate = useNavigate()

  useEffect(() => {
    if (!currentMatch) navigate('/')
  }, [currentMatch, navigate])

  const createLobbyFromMatch = () => {
    // Create a lobby for matched players
    send('lobby.create', {
      name: `Match ${currentMatch?.match_id.slice(0, 8)}`,
      game_mode: currentMatch?.game_mode,
      max_players: currentMatch?.players.length ?? 2,
    })
  }

  if (!currentMatch) return null

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="glass rounded-2xl p-10 max-w-md w-full text-center space-y-6">
        <div className="inline-flex p-5 rounded-full bg-green-500/20 border border-green-500/40">
          <Swords className="w-10 h-10 text-green-400" />
        </div>

        <div>
          <h1 className="text-3xl font-bold text-white">Match Found!</h1>
          <p className="text-slate-400 mt-1 capitalize">{currentMatch.game_mode} match</p>
        </div>

        <div className="glass rounded-xl p-4 text-left">
          <div className="flex items-center gap-2 text-sm text-slate-400 mb-3">
            <Users className="w-4 h-4" />
            Players in match
          </div>
          <div className="space-y-2">
            {currentMatch.players.map((pid, i) => (
              <div key={`${pid}-${i}`} className="flex items-center gap-3 text-sm">
                <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold">
                  {i + 1}
                </div>
                <span className="text-slate-300 font-mono text-xs">{pid}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={createLobbyFromMatch}
            className="flex-1 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold transition-all glow"
          >
            Create Lobby
          </button>
          <button
            onClick={() => navigate('/')}
            className="flex-1 py-3 rounded-xl bg-surface-700 hover:bg-surface-600 text-slate-300 font-semibold transition-all"
          >
            Back to Menu
          </button>
        </div>
      </div>
    </div>
  )
}
