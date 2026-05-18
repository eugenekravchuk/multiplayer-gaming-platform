"""Shared types and models."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from enum import Enum


class PlayerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    IN_GAME = "in_game"
    IN_LOBBY = "in_lobby"
    MATCHMAKING = "matchmaking"


class GameMode(str, Enum):
    CASUAL = "casual"
    RANKED = "ranked"
    TOURNAMENT = "tournament"
    CUSTOM = "custom"


class Player(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    username: str
    email: Optional[str] = None
    status: PlayerStatus = PlayerStatus.OFFLINE
    rating: int = 1000
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class MatchRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    player_id: UUID
    game_mode: GameMode
    rating: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    region: str = "default"


class Match(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    players: List[UUID]
    game_mode: GameMode
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lobby_id: Optional[UUID] = None
    session_id: Optional[UUID] = None


class Lobby(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    host_id: UUID
    players: List[UUID] = Field(default_factory=list)
    max_players: int = 8
    game_mode: GameMode
    is_ready: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = Field(default_factory=dict)


class GameState(BaseModel):
    session_id: UUID
    players: Dict[UUID, Dict[str, Any]]
    game_data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = 0


class GameSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    match_id: UUID
    players: List[UUID]
    game_mode: GameMode = GameMode.CASUAL
    state: GameState
    status: str = "active"  # active, paused, ended
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    channel_id: str
    sender_id: UUID
    sender_username: Optional[str] = None
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class Notification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    recipient_id: UUID
    title: str
    message: str
    type: str
    read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[Dict[str, Any]] = None


class LeaderboardEntry(BaseModel):
    player_id: UUID
    username: str
    score: int
    wins: int = 0
    losses: int = 0
    rank: Optional[int] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
