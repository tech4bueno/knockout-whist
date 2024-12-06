from typing import List, Tuple, Optional

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
        """Determine winner with duplicate card handling.
        Priority: Trumps > led suit > other suits.
        For identical cards, the first player to play the card wins."""

        return max(
            self.plays,
            key=lambda play_with_index: (
                play_with_index[1].suit == trump_suit,  # Trump suit priority
                play_with_index[1].suit == self.led_suit,  # Led suit priority
                play_with_index[1].rank,  # Card rank
                -self.plays.index(play_with_index)  # Play order
        ))[0]
