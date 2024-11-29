import json
import websockets
from datetime import datetime
from collections import defaultdict

from rich.console import Console
from rich.table import Table
from rich import box


class DebugWebSocket:
    _message_history = defaultdict(list)
    _console = Console()

    def __init__(self, ws: websockets.WebSocketServerProtocol):
        self._ws = ws
        self.player_name = None

    async def send(self, message: str):
        try:
            data = json.loads(message)
            timestamp = datetime.now().strftime("%H:%M:%S")

            self._message_history[self.player_name].append((">>>", timestamp, data))

            self._print_message_table()
            await self._ws.send(message)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {message}")
            await self._ws.send(message)

    async def recv(self) -> str:
        message = await self._ws.recv()
        try:
            data = json.loads(message)
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Capture player name from join/create messages
            if data.get("type") in ["create", "join"]:
                self.player_name = data.get("name", "Unknown")

            if self.player_name:
                self._message_history[self.player_name].append(("<<<", timestamp, data))
            else:
                self._message_history["Unknown"].append(("<<<", timestamp, data))

            self._print_message_table()
            return message
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {message}")
            return message

    def _print_message_table(self):
        self._console.clear()
        table = Table(title="WebSocket Message History", box=box.ROUNDED)

        # Add columns for timestamp and all players
        table.add_column("Time", style="cyan")
        table.add_column("Dir", style="magenta")
        for player in sorted(self._message_history.keys()):
            table.add_column(player, style="green")

        # Get all timestamps to create rows
        all_timestamps = set()
        for messages in self._message_history.values():
            all_timestamps.update(msg[1] for msg in messages)

        # Create rows ordered by timestamp
        for timestamp in sorted(all_timestamps):
            row = [timestamp]

            # Find direction for this timestamp (assuming it's the same for all players)
            direction = next(
                (
                    msg[0]
                    for player_msgs in self._message_history.values()
                    for msg in player_msgs
                    if msg[1] == timestamp
                ),
                "",
            )
            row.append(direction)

            # Add message for each player at this timestamp
            for player in sorted(self._message_history.keys()):
                message = ""
                for dir, ts, msg in self._message_history[player]:
                    if ts == timestamp:
                        message = json.dumps(msg, indent=2)
                row.append(message)

            table.add_row(*row)

        self._console.print(table)

    def __getattr__(self, attr):
        return getattr(self._ws, attr)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            message = await self.recv()
            return message
        except websockets.exceptions.ConnectionClosed:
            raise StopAsyncIteration
