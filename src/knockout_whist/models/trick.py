from typing import List, Optional, Tuple

from .card import Card
from .player import Player


class Trick:
    def __init__(self):
        self.plays: List[Tuple[Player, Card]] = []
        self.led_suit: Optional[str] = None

    def add_play(self, player: Player, card: Card) -> None:
        if not self.plays:
            self.led_suit = card.suit
        self.plays.append((player, card))

    def is_complete(self, player_count: int) -> bool:
        return len(self.plays) == player_count

    def determine_winner(self, trump_suit: str) -> Player:
        return max(
            self.plays,
            key=lambda pc: (
                pc[1].suit == trump_suit,
                pc[1].suit == self.led_suit,
                pc[1].rank,
            ),
        )[0]
