export interface Player {
  player_id: string
  username: string
  status?: string
}

export interface Lobby {
  id: string
  name: string
  host_id: string
  players: string[]
  max_players: number
  game_mode: string
  is_ready: boolean
  created_at: string
  settings: Record<string, unknown>
}

export interface Match {
  match_id: string
  players: string[]
  game_mode: string
}

export interface GameState {
  session_id: string
  players: Record<string, { health: number; score: number; position: { x: number; y: number } }>
  game_data: Record<string, unknown>
  timestamp: string
  version: number
}

export interface GameSession {
  id: string
  match_id: string
  players: string[]
  state: GameState
  status: string
}

export interface ChatMessage {
  id: string
  channel_id: string
  sender_id: string
  content: string
  timestamp: string
  metadata?: Record<string, unknown> | null
}

export interface Notification {
  id: string
  recipient_id: string
  title: string
  message: string
  type: string
  read: boolean
  created_at: string
}

export interface LeaderboardEntry {
  player_id: string
  username: string
  score: number
  wins: number
  losses: number
  rank?: number
}

export type WSMessage =
  | { type: 'connected'; data: { player_id: string; message: string } }
  | { type: 'matchmaking.queued'; data: { message: string } }
  | { type: 'match.found'; data: Match }
  | { type: 'lobby.created'; data: { lobby_id: string; lobby: Lobby } }
  | { type: 'lobby.player_joined'; data: { lobby_id: string; player_id: string; players: string[] } }
  | { type: 'lobby.player_left'; data: { lobby_id: string; player_id: string; players: string[] } }
  | { type: 'lobby.all_ready'; data: { lobby_id: string; message: string } }
  | { type: 'lobby.join_failed'; data: { message: string } }
  | { type: 'session.started'; data: { session_id: string; state: GameState } }
  | { type: 'game.state_update'; data: { session_id: string; state: GameState; last_action: unknown } }
  | { type: 'chat.joined'; data: { channel_id: string; message: string } }
  | { type: 'chat.history'; data: { channel_id: string; messages: ChatMessage[] } }
  | { type: 'chat.message'; data: { channel_id: string; message: ChatMessage } }
  | { type: 'chat.system'; data: { channel_id: string; message: string } }
  | { type: 'notification.new'; data: { notification: Notification; unread_count: number } }
  | { type: 'score.updated'; data: { session_id: string; new_score: number; wins: number; losses: number } }
  | { type: 'ranking.changed'; data: { old_rank: number; new_rank: number; category: string } }
  | { type: 'error'; data: { message: string } }
