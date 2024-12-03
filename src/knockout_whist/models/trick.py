from typing import List, Optional, Tuple

from .card import Card


class Trick:
    def __init__(self):
        self.plays: List[Tuple["Player", Card]] = []

    @property
    def led_suit(self) -> Optional[str]:
        return self.plays[0][1].suit if self.plays else None

    def add_play(self, player: "Player", card: Card) -> None:
        self.plays.append((player, card))

    def is_complete(self, player_count: int) -> bool:
        return len(self.plays) == player_count

    def determine_winner(self, trump_suit: str) -> "Player":
        """Trumps > led suit > other suits"""
        return max(
            self.plays,
            key=lambda pc: (
                pc[1].suit == trump_suit,
                pc[1].suit == self.led_suit,
                pc[1].rank,
            ),
        )[0]
