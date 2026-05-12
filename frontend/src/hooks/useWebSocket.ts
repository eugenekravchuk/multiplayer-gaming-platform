import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useGameStore } from '../store/gameStore'
import type { WSMessage } from '../types'

const WS_URL = 'ws://localhost:3000/ws'

let socket: WebSocket | null = null

export function useWebSocket() {
  const navigate = useNavigate()
  const { token } = useAuthStore()
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  const {
    setMatchmakingStatus,
    setCurrentMatch,
    setCurrentLobby,
    updateLobbyPlayers,
    setCurrentSession,
    updateSessionState,
    addMessage,
    setMessages,
    addNotification,
    setUnreadCount,
  } = useGameStore()

  const send = useCallback((type: string, data: Record<string, unknown> = {}) => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type, data }))
    }
  }, [])

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'connected':
        break

      case 'matchmaking.queued':
        setMatchmakingStatus('searching')
        break

      case 'match.found':
        setCurrentMatch(msg.data)
        setMatchmakingStatus('found')
        navigate('/match-found')
        break

      case 'lobby.created':
        setCurrentLobby(msg.data.lobby)
        navigate('/lobby')
        break

      case 'lobby.player_joined':
      case 'lobby.player_left':
        updateLobbyPlayers(msg.data.players)
        break

      case 'lobby.all_ready':
        break

      case 'lobby.join_failed':
        alert(`Failed to join lobby: ${msg.data.message}`)
        break

      case 'session.started':
        setCurrentSession({
          id: msg.data.session_id,
          match_id: '',
          players: [],
          state: msg.data.state,
          status: 'active',
        })
        navigate('/game')
        break

      case 'game.state_update':
        updateSessionState(msg.data.state)
        break

      case 'chat.history':
        setMessages(msg.data.channel_id, msg.data.messages)
        break

      case 'chat.message':
        addMessage(msg.data.channel_id, msg.data.message)
        break

      case 'notification.new':
        addNotification(msg.data.notification)
        setUnreadCount(msg.data.unread_count)
        break

      case 'error':
        console.error('Server error:', msg.data.message)
        break
    }
  }, [navigate, setMatchmakingStatus, setCurrentMatch, setCurrentLobby,
      updateLobbyPlayers, setCurrentSession, updateSessionState,
      addMessage, setMessages, addNotification, setUnreadCount])

  useEffect(() => {
    if (!token || socket) return

    const connect = () => {
      socket = new WebSocket(`${WS_URL}?token=${token}`)

      socket.onopen = () => {
        console.log('WebSocket connected')
        // Join global chat
        socket?.send(JSON.stringify({ type: 'chat.join', data: { channel_id: 'global' } }))
      }

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage
          handleMessage(msg)
        } catch (e) {
          console.error('Failed to parse WS message', e)
        }
      }

      socket.onclose = () => {
        socket = null
        // Reconnect after 3s
        reconnectTimeout.current = setTimeout(connect, 3000)
      }

      socket.onerror = (e) => {
        console.error('WebSocket error', e)
        socket?.close()
      }
    }

    connect()

    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
    }
  }, [token, handleMessage])

  return { send, connected: socket?.readyState === WebSocket.OPEN }
}
