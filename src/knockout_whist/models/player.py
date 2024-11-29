import json
from dataclasses import dataclass, field
from typing import List

import websockets

from .card import Card

@dataclass
class Player:
    ws: websockets.WebSocketServerProtocol
    name: str
    hand: List[Card] = field(default_factory=list)
    tricks_won: int = 0

    async def send_message(self, message: dict) -> None:
        await self.ws.send(json.dumps(message))
