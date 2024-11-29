import json
from dataclasses import dataclass, field
from typing import List

from aiohttp import web

from .card import Card


@dataclass
class Player:
    ws: web.WebSocketResponse
    name: str
    hand: List[Card] = field(default_factory=list)
    tricks_won: int = 0
