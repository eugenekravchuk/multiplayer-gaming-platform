"""
Simple WebSocket test client for the Gaming Platform.
Usage: python test_client.py
"""
import asyncio
import json
import sys
import httpx
import websockets


GATEWAY_URL = "ws://localhost:3000/ws"
GATEWAY_HTTP = "http://localhost:3000"


async def test_client(username: str):
    """Test client that connects and performs basic interactions."""
    
    # Get real JWT token from auth endpoint
    print(f"Logging in as {username}...")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{GATEWAY_HTTP}/auth/login", json={
            "username": username,
            "password": "password"
        })
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return
        auth = response.json()
        token = auth["token"]
        player_id = auth["player_id"]
    
    uri = f"{GATEWAY_URL}?token={token}"
    
    print(f"Connecting as {username} (ID: {player_id})...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected! Waiting for messages...")
            
            # Handle incoming messages
            async def receive_messages():
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        print(f"[RECEIVED] {json.dumps(data, indent=2)}")
                    except websockets.exceptions.ConnectionClosed:
                        print("Connection closed")
                        break
            
            # Start receiving in background
            receive_task = asyncio.create_task(receive_messages())
            
            # Interactive command loop
            while True:
                print("\nCommands:")
                print("1 - Join matchmaking (casual)")
                print("2 - Join matchmaking (ranked)")
                print("3 - Cancel matchmaking")
                print("4 - Create lobby")
                print("5 - Join lobby")
                print("6 - Send chat message")
                print("7 - Set ready in lobby")
                print("8 - Send game action")
                print("q - Quit")
                
                cmd = await asyncio.get_event_loop().run_in_executor(
                    None, input, "\nEnter command: "
                )
                
                if cmd == "1":
                    await websocket.send(json.dumps({
                        "type": "matchmaking.join",
                        "data": {"game_mode": "casual", "rating": 1000}
                    }))
                    print("Sent: Join matchmaking (casual)")
                
                elif cmd == "2":
                    await websocket.send(json.dumps({
                        "type": "matchmaking.join",
                        "data": {"game_mode": "ranked", "rating": 1200}
                    }))
                    print("Sent: Join matchmaking (ranked)")
                
                elif cmd == "3":
                    await websocket.send(json.dumps({
                        "type": "matchmaking.cancel",
                        "data": {}
                    }))
                    print("Sent: Cancel matchmaking")
                
                elif cmd == "4":
                    name = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Lobby name: "
                    )
                    await websocket.send(json.dumps({
                        "type": "lobby.create",
                        "data": {"name": name, "game_mode": "casual", "max_players": 4}
                    }))
                    print("Sent: Create lobby")
                
                elif cmd == "5":
                    lobby_id = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Lobby ID: "
                    )
                    await websocket.send(json.dumps({
                        "type": "lobby.join",
                        "data": {"lobby_id": lobby_id}
                    }))
                    print("Sent: Join lobby")
                
                elif cmd == "6":
                    channel = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Channel (default: global): "
                    ) or "global"
                    content = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Message: "
                    )
                    await websocket.send(json.dumps({
                        "type": "chat.message",
                        "data": {"channel_id": channel, "content": content}
                    }))
                    print("Sent: Chat message")
                
                elif cmd == "7":
                    lobby_id = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Lobby ID: "
                    )
                    await websocket.send(json.dumps({
                        "type": "lobby.ready",
                        "data": {"lobby_id": lobby_id, "ready": True}
                    }))
                    print("Sent: Set ready")
                
                elif cmd == "8":
                    session_id = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Session ID: "
                    )
                    action_type = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Action type (move/attack/score): "
                    )
                    await websocket.send(json.dumps({
                        "type": "game.action",
                        "data": {
                            "session_id": session_id,
                            "action": {"type": action_type, "data": {}}
                        }
                    }))
                    print("Sent: Game action")
                
                elif cmd.lower() == "q":
                    print("Disconnecting...")
                    receive_task.cancel()
                    break
                
                else:
                    print("Unknown command")
                
                # Wait a bit for response
                await asyncio.sleep(0.5)
    
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("Enter username: ") or "test_player"
    
    await test_client(username)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
