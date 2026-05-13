import { useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useGameStore } from '../store/gameStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuthStore } from '../store/authStore'

export default function GamePage() {
  const { currentSession } = useGameStore()
  const { send } = useWebSocket()
  const { playerId } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!currentSession) navigate('/')
  }, [currentSession, navigate])

  if (!currentSession) return null

  const { state } = currentSession
  const gameData = state.game_data || {}
  const status = gameData.status || 'waiting'
  const players = Object.entries(state.players || {})

  const opponentId = players.find(([id]) => id !== playerId)?.[0]
  
  const myScore = playerId && state.players?.[playerId]?.score || 0
  const oppScore = opponentId && state.players?.[opponentId]?.score || 0

  const sendAction = (move: 'rock' | 'paper' | 'scissors') => {
    send('game.action', {
      session_id: currentSession.id,
      action: { type: 'rps_move', move },
    })
  }

  const renderStatus = () => {
    switch (status) {
      case 'countdown':
        return <h2 className="text-3xl font-bold text-yellow-400 animate-pulse text-center my-8">Get Ready... Round {gameData.round || 1}</h2>
      case 'in_progress':
        const myMove = gameData.moves?.[playerId || '']
        if (myMove) {
          return <h2 className="text-xl font-bold text-brand-400 text-center my-8">Waiting for opponent...</h2>
        }
        return (
          <div className="flex justify-center gap-4 my-8">
            {['rock', 'paper', 'scissors'].map((m) => (
              <button
                key={m}
                onClick={() => sendAction(m as 'rock' | 'paper' | 'scissors')}
                className="w-24 h-24 rounded-2xl glass hover:bg-brand-500/20 flex flex-col items-center justify-center transition-all border border-brand-500/30 capitalize text-lg font-bold"
              >
                {m === 'rock' && '✊'}
                {m === 'paper' && '✋'}
                {m === 'scissors' && '✌️'}
                <span className="mt-2 text-sm text-slate-300">{m}</span>
              </button>
            ))}
          </div>
        )
      case 'round_finished':
        const lastWinner = gameData.last_round_winner
        let msg = "It's a tie!"
        let color = "text-yellow-400"
        if (lastWinner === playerId) {
          msg = "You won the round!"
          color = "text-green-400"
        } else if (lastWinner && lastWinner !== 'tie') {
          msg = "Opponent won the round!"
          color = "text-red-400"
        }
        return <h2 className={`text-2xl font-bold text-center my-8 ${color}`}>{msg}</h2>
      case 'game_finished':
        const gameWinner = gameData.winner
        const winMsg = gameWinner === playerId ? "You won the game! 🏆" : "You lost the game! 💀"
        const winColor = gameWinner === playerId ? "text-green-500" : "text-red-500"
        return (
          <div className="text-center my-8 space-y-4">
            <h2 className={`text-4xl font-black ${winColor}`}>{winMsg}</h2>
            {gameData.finish_reason === 'disconnect' && <p className="text-slate-400">Opponent disconnected.</p>}
            <button
              onClick={() => navigate('/')}
              className="mt-4 px-6 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium"
            >
              Back to Dashboard
            </button>
          </div>
        )
      default:
        return <h2 className="text-xl text-center my-8 text-slate-400">Waiting...</h2>
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between p-4 glass rounded-xl">
        <div className="text-center flex-1">
          <p className="text-sm text-slate-400 uppercase tracking-wider font-bold mb-1">You</p>
          <p className="text-4xl font-black text-brand-400">{myScore}</p>
        </div>
        
        <div className="text-2xl font-black text-slate-500 px-4">VS</div>
        
        <div className="text-center flex-1">
          <p className="text-sm text-slate-400 uppercase tracking-wider font-bold mb-1">Opponent</p>
          <p className="text-4xl font-black text-red-400">{oppScore}</p>
        </div>
      </div>

      <div className="glass rounded-xl p-8 min-h-[300px] flex flex-col justify-center">
        {renderStatus()}
      </div>

      {status !== 'game_finished' && (
        <div className="text-center">
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 rounded-lg bg-surface-700 hover:bg-surface-600 text-slate-400 text-sm transition-all"
          >
            Leave Match
          </button>
        </div>
      )}
    </div>
  )
}
