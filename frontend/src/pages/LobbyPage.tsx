import { useState, useEffect } from 'react'
import { Users, Plus, LogIn, Crown, Check, Play, Copy } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useGameStore } from '../store/gameStore'
import { useAuthStore } from '../store/authStore'

const API = 'http://localhost:3000'

export default function LobbyPage() {
  const [lobbyName, setLobbyName] = useState('')
  const [joinId, setJoinId] = useState('')
  const [activeTab, setActiveTab] = useState<'create' | 'join' | 'current'>('current')
  const [lobbies, setLobbies] = useState<{ id: string; name: string; player_count: number; max_players: number; game_mode: string }[]>([])
  const [ready, setReady] = useState(false)
  const { send } = useWebSocket()
  const { currentLobby } = useGameStore()
  const { playerId } = useAuthStore()

  // Switch to current tab when we have a lobby
  useEffect(() => {
    if (currentLobby) setActiveTab('current')
  }, [currentLobby])

  // Fetch lobbies from API
  useEffect(() => {
    if (activeTab === 'join') {
      fetch(`${API}/lobbies`)
        .then((r) => r.json())
        .then((d) => setLobbies(d.lobbies ?? []))
        .catch(() => {})
    }
  }, [activeTab])

  const createLobby = () => {
    if (!lobbyName.trim()) return
    send('lobby.create', { name: lobbyName.trim(), game_mode: 'casual', max_players: 2 })
    setLobbyName('')
  }

  const joinLobby = (id: string) => {
    send('lobby.join', { lobby_id: id })
  }

  const leaveLobby = () => {
    if (!currentLobby) return
    send('lobby.leave', { lobby_id: currentLobby.id })
  }

  const toggleReady = () => {
    if (!currentLobby) return
    const newReady = !ready
    setReady(newReady)
    send('lobby.ready', { lobby_id: currentLobby.id, ready: newReady })
  }

  const copyId = () => {
    if (currentLobby) navigator.clipboard.writeText(currentLobby.id)
  }

  const tabs = [
    { id: 'current', label: 'Current Lobby' },
    { id: 'create', label: 'Create' },
    { id: 'join', label: 'Browse' },
  ] as const

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Lobbies</h1>
        <p className="text-slate-400 mt-1">Create or join a game lobby</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-surface-800 rounded-xl">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-brand-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Current Lobby */}
      {activeTab === 'current' && (
        <div>
          {!currentLobby ? (
            <div className="glass rounded-xl p-10 text-center">
              <Users className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400">You're not in a lobby</p>
              <button
                onClick={() => setActiveTab('create')}
                className="mt-4 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm transition-all"
              >
                Create one
              </button>
            </div>
          ) : (
            <div className="glass rounded-xl overflow-hidden">
              <div className="p-5 border-b border-surface-700 flex items-center justify-between">
                <div>
                  <h2 className="font-bold text-white text-lg">{currentLobby.name}</h2>
                  <p className="text-xs text-slate-500 capitalize">{currentLobby.game_mode} · {currentLobby.players.length}/{currentLobby.max_players} players</p>
                </div>
                <button onClick={copyId} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-brand-400 transition-colors">
                  <Copy className="w-3.5 h-3.5" />
                  Copy ID
                </button>
              </div>

              <div className="p-5 space-y-3">
                {currentLobby.players.map((player, i) => (
                  <div key={player.id} className="flex items-center gap-3 p-3 bg-surface-700/50 rounded-lg">
                    <div className="w-8 h-8 rounded-full bg-brand-600/60 flex items-center justify-center text-sm font-bold">
                      {i + 1}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-bold text-white">{player.username}</p>
                      <p className="text-[10px] text-slate-500 font-mono">{player.id.slice(-12)}</p>
                    </div>
                    {player.id === currentLobby.host_id && (
                      <div className="flex items-center gap-1 text-xs text-yellow-400">
                        <Crown className="w-3.5 h-3.5" />
                        Host
                      </div>
                    )}
                    {player.id === playerId && (
                      <span className="text-xs text-brand-400 font-medium">You</span>
                    )}
                  </div>
                ))}
              </div>

              <div className="p-5 border-t border-surface-700 flex gap-3">
                <button
                  onClick={toggleReady}
                  className={`flex-1 py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 ${
                    ready
                      ? 'bg-green-600 hover:bg-green-500 text-white'
                      : 'bg-surface-700 hover:bg-surface-600 text-slate-300'
                  }`}
                >
                  <Check className="w-4 h-4" />
                  {ready ? 'Ready!' : 'Set Ready'}
                </button>
                <button
                  onClick={leaveLobby}
                  className="px-4 py-3 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-red-400 font-semibold transition-all"
                >
                  Leave
                </button>
              </div>

              {currentLobby.players.length >= 2 && (
                <div className="px-5 pb-5">
                  <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 rounded-lg p-3">
                    <Play className="w-3.5 h-3.5" />
                    All players ready → game starts automatically!
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Create Lobby */}
      {activeTab === 'create' && (
        <div className="glass rounded-xl p-6 space-y-4">
          <h2 className="font-semibold text-slate-300 flex items-center gap-2">
            <Plus className="w-4 h-4" /> Create New Lobby
          </h2>
          <div>
            <label className="block text-sm text-slate-400 mb-1.5">Lobby Name</label>
            <input
              value={lobbyName}
              onChange={(e) => setLobbyName(e.target.value)}
              placeholder="e.g. Pro Squad Only"
              onKeyDown={(e) => e.key === 'Enter' && createLobby()}
              className="w-full bg-surface-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 outline-none focus:ring-2 focus:ring-brand-500 transition-all"
            />
          </div>
          <button
            onClick={createLobby}
            disabled={!lobbyName.trim()}
            className="w-full py-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white font-semibold transition-all"
          >
            Create Lobby
          </button>
        </div>
      )}

      {/* Browse Lobbies */}
      {activeTab === 'join' && (
        <div className="space-y-4">
          {/* Join by ID */}
          <div className="glass rounded-xl p-4 flex gap-3">
            <input
              value={joinId}
              onChange={(e) => setJoinId(e.target.value)}
              placeholder="Paste lobby ID..."
              className="flex-1 bg-surface-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:ring-2 focus:ring-brand-500"
            />
            <button
              onClick={() => joinLobby(joinId)}
              disabled={!joinId.trim()}
              className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white text-sm font-medium transition-all flex items-center gap-1.5"
            >
              <LogIn className="w-4 h-4" /> Join
            </button>
          </div>

          {/* Lobby list */}
          {lobbies.length === 0 ? (
            <div className="glass rounded-xl p-10 text-center">
              <p className="text-slate-500">No open lobbies found</p>
            </div>
          ) : (
            <div className="space-y-2">
              {lobbies.map((lobby) => (
                <div key={lobby.id} className="glass rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-white">{lobby.name}</p>
                    <p className="text-xs text-slate-500 capitalize">
                      {lobby.game_mode} · {lobby.player_count}/{lobby.max_players} players
                    </p>
                  </div>
                  <button
                    onClick={() => joinLobby(lobby.id)}
                    className="px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-all"
                  >
                    Join
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
