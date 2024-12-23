from dataclasses import dataclass, field
from typing import List

from aiohttp import web

from .card import Card
from ..ai.game_ai import GameAI


@dataclass
class Player:
    ws: web.WebSocketResponse
    name: str
    hand: List[Card] = field(default_factory=list)
    tricks_won: int = 0

    def sort_hand(self):
        """Group cards by suit and sort lowest to highest."""
        suit_order = {"♦": 0, "♣": 1, "♥": 2, "♠": 3}
        self.hand.sort(key=lambda card: (suit_order[card.suit], card.rank))


class HumanPlayer(Player):
    def __init__(self, ws: web.WebSocketResponse, name: str, hand: List[Card]):
        super().__init__(ws, name, hand)
        self.is_ai = False


class AIPlayer(Player):
    def __init__(self, name: str):
        super().__init__(None, name, [])  # No websocket
        self.ai = GameAI(self)
        self.is_ai = True
