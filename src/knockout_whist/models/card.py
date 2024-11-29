from dataclasses import dataclass


@dataclass
class Card:
    suit: str
    rank: int

    def __str__(self) -> str:
        ranks = {11: "J", 12: "Q", 13: "K", 14: "A"}
        rank_str = ranks.get(self.rank, str(self.rank))
        return f"{rank_str}{self.suit}"

    @classmethod
    def from_string(cls, card_str: str) -> "Card":
        """Parse card string like 'A♥' into a Card instance."""
        rank_str = card_str[:-1]
        suit = card_str[-1]
        try:
            rank = int(rank_str)
        except ValueError:
            rank = {"J": 11, "Q": 12, "K": 13, "A": 14}[rank_str]
        return cls(suit=suit, rank=rank)
