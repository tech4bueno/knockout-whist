from typing import List, Optional

from ..models.card import Card
from ..models.trick import Trick


class GameAI:
    def __init__(self, player: "Player"):
        self.player = player

    def choose_trump(self) -> str:
        """Choose a trump suit based on the strongest suit in hand."""
        suit_counts = {suit: 0 for suit in "♠♥♦♣"}
        suit_strength = {suit: 0 for suit in "♠♥♦♣"}

        # Calculate both the count and total strength of each suit
        for card in self.player.hand:
            suit_counts[card.suit] += 1
            suit_strength[card.suit] += card.rank

        # Weight the decision based on both count and strength
        suit_scores = {
            suit: (count * 10 + strength)
            for suit, (count, strength) in
            zip(suit_counts.keys(), zip(suit_counts.values(), suit_strength.values()))
        }

        return max(suit_scores.items(), key=lambda x: x[1])[0]

    def choose_card(self, current_trick: Trick, trump_suit: str) -> Card:
        """Choose which card to play based on the current trick state."""
        playable_cards = self._get_playable_cards(current_trick)

        if not current_trick.plays:
            return self._lead_card(trump_suit)

        return self._follow_card(playable_cards, current_trick, trump_suit)

    def _get_playable_cards(self, current_trick: Trick) -> List[Card]:
        """Get list of legally playable cards."""
        if not current_trick.plays:
            return self.player.hand

        # Must follow suit if possible
        same_suit_cards = [
            card for card in self.player.hand
            if card.suit == current_trick.led_suit
        ]
        return same_suit_cards if same_suit_cards else self.player.hand

    def _lead_card(self, trump_suit: str) -> Card:
        """Choose a card to lead the trick."""
        non_trump_cards = [c for c in self.player.hand if c.suit != trump_suit]

        # If we have non-trump high cards, lead those
        high_cards = [c for c in non_trump_cards if c.rank >= 12]
        if high_cards:
            return max(high_cards, key=lambda c: c.rank)

        # If we have only low cards, lead lowest
        if non_trump_cards:
            return min(non_trump_cards, key=lambda c: c.rank)

        # If we only have trump cards, lead lowest trump
        return min(self.player.hand, key=lambda c: c.rank)

    def _follow_card(self, playable_cards: List[Card], current_trick: Trick, trump_suit: str) -> Card:
        """Choose a card to follow in a trick."""
        winning_card = self._get_current_winning_card(current_trick, trump_suit)

        # Try to win the trick if possible
        winning_cards = [
            card for card in playable_cards
            if self._card_beats(card, winning_card, trump_suit)
        ]

        if winning_cards:
            # Win with lowest possible winning card
            return min(winning_cards, key=lambda c: c.rank)

        # If we can't win, play our lowest card
        return min(playable_cards, key=lambda c: c.rank)

    def _get_current_winning_card(self, trick: Trick, trump_suit: str) -> Optional[Card]:
        """Determine which card is currently winning the trick."""
        if not trick.plays:
            return None

        winning_card = trick.plays[0][1]
        for _, card in trick.plays[1:]:
            if self._card_beats(card, winning_card, trump_suit):
                winning_card = card
        return winning_card

    def _card_beats(self, card1: Card, card2: Card, trump_suit: str) -> bool:
        """Determine if card1 beats card2."""
        if card1.suit == trump_suit and card2.suit != trump_suit:
            return True
        if card2.suit == trump_suit and card1.suit != trump_suit:
            return False
        if card1.suit != card2.suit:
            return False
        return card1.rank > card2.rank
