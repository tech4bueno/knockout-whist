import asyncio
import json
import random
import string
from typing import List, Optional, Dict
from aiohttp import web, WSMsgType

from ..models.card import Card
from ..models.player import Player
from ..models.trick import Trick

class GameState:
    WAITING = "waiting"
    CHOOSING_TRUMP = "choosing_trump"
    PLAYING = "playing"
    FINISHED = "finished"

class GameError(Exception):
    pass

class Game:
    def __init__(self, code: str):
        self.code = code
        self.players: List[Player] = []
        self.state = GameState.WAITING
        self.current_round = 7
        self.trump_suit: Optional[str] = None
        self.current_trick = Trick()
        self.current_player_idx = 0
        self.trick_starter_idx = 0
        self.trump_chooser: Optional[Player] = None

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def create_deck(self) -> List[Card]:
        """Create and shuffle a new deck of cards."""
        deck = [Card(suit, rank) for suit in "♠♥♦♣" for rank in range(2, 15)]
        random.shuffle(deck)
        return deck

    async def deal_cards(self) -> None:
        """Deal cards to all players for the current round."""
        deck = self.create_deck()
        for player in self.players:
            player.hand = [deck.pop() for _ in range(self.current_round)]
            player.tricks_won = 0

        await self.broadcast_game_state()

    async def broadcast_game_state(self) -> None:
        """Send current game state to all players."""
        for player in self.players:
            await player.send_message({
                "type": "gameState",
                "state": self.get_game_state(player)
            })

    async def start_trump_selection(self) -> None:
        """Start the trump selection phase of the round."""
        self.state = GameState.CHOOSING_TRUMP
        await self.deal_cards()

        if self.current_round == 7:
            self.trump_suit = random.choice(["♠", "♥", "♦", "♣"])
            await self.start_round()
        else:
            await self.broadcast({
                "type": "trumpSelection",
                "chooser": self.trump_chooser.name,
                "gameState": self.get_game_state()
            })

    async def start_round(self) -> None:
        """Start a new round after trump has been selected."""
        self.state = GameState.PLAYING
        self.current_trick = Trick()
        self.current_player_idx = self.trick_starter_idx

        await self.broadcast({
            "type": "roundStart",
            "gameState": self.get_game_state()
        })

        await self.broadcast_game_state()

    async def handle_trump_selection(self, player: Player, suit: str) -> None:
        """Handle a player's trump suit selection."""
        if self.state != GameState.CHOOSING_TRUMP:
            raise GameError("Not in trump selection phase")

        if player != self.trump_chooser:
            raise GameError("Not your turn to choose trump")

        if suit not in "♠♥♦♣":
            raise GameError("Invalid suit")

        self.trump_suit = suit
        await self.start_round()

    async def play_card(self, player: Player, card_str: str) -> None:
        """Handle a player playing a card."""
        card = Card.from_string(card_str)
        self.validate_play(player, card)

        player.hand = [c for c in player.hand if not (c.suit == card.suit and c.rank == card.rank)]
        self.current_trick.add_play(player, card)

        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)

        await self.broadcast({
            "type": "cardPlayed",
            "player": player.name,
            "card": card_str,
            "nextPlayer": self.current_player.name,
            "gameState": self.get_game_state()
        })

        if self.current_trick.is_complete(len(self.players)):
            await self.handle_trick_completion()

    async def handle_trick_completion(self) -> None:
        """Handle the completion of a trick."""
        await self.broadcast({
            "type": "trickComplete",
            "gameState": self.get_game_state()
        })

        winner = self.current_trick.determine_winner(self.trump_suit)
        winner.tricks_won += 1

        await asyncio.sleep(2)

        await self.broadcast({
            "type": "trickWinner",
            "winner": winner.name,
            "gameState": self.get_game_state()
        })

        self.current_player_idx = self.players.index(winner)
        self.trick_starter_idx = self.current_player_idx
        self.current_trick = Trick()

        await asyncio.sleep(1)

        if not any(len(p.hand) > 0 for p in self.players):
            await self.handle_round_end()
        else:
            await self.broadcast({
                "type": "nextTrick",
                "gameState": self.get_game_state()
            })

    async def handle_round_end(self) -> None:
        """Handle the end of a round, including player elimination."""
        self.players = [p for p in self.players if p.tricks_won > 0]

        if len(self.players) <= 1 or self.current_round <= 1:
            self.state = GameState.FINISHED
            if self.players:
                await self.broadcast({
                    "type": "gameOver",
                    "winner": self.players[0].name,
                    "gameState": self.get_game_state()
                })
            return

        self.current_round -= 1
        max_tricks = max(p.tricks_won for p in self.players)
        potential_choosers = [p for p in self.players if p.tricks_won == max_tricks]
        self.trump_chooser = random.choice(potential_choosers)
        self.trump_suit = None

        await self.broadcast({
            "type": "roundEnd",
            "trumpChooser": self.trump_chooser.name,
            "gameState": self.get_game_state()
        })

        await self.start_trump_selection()

    def validate_play(self, player: Player, card: Card) -> None:
        """Validate if a card play is legal."""
        if self.state != GameState.PLAYING:
            raise GameError("Not time to play")

        if player != self.current_player:
            raise GameError("Not your turn")

        if not any(c.suit == card.suit and c.rank == card.rank for c in player.hand):
            raise GameError("Card not in hand")

        if self.current_trick.plays and player.hand:
            if any(c.suit == self.current_trick.led_suit for c in player.hand) and card.suit != self.current_trick.led_suit:
                raise GameError("Must follow suit")

    def get_game_state(self, for_player: Optional[Player] = None) -> dict:
        """Get the current game state, optionally including player-specific information."""
        state = {
            "code": self.code,
            "currentRound": self.current_round,
            "trumpSuit": self.trump_suit,
            "currentTrick": [(p.name, str(c)) for p, c in self.current_trick.plays],
            "players": [
                {"name": p.name, "trickCount": p.tricks_won}
                for p in self.players
            ],
            "state": self.state,
            "currentPlayer": self.current_player.name if self.state == GameState.PLAYING else None,
            "trumpChooser": self.trump_chooser.name if self.trump_chooser else None,
        }

        if for_player:
            state["hand"] = [str(c) for c in for_player.hand]

        return state

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all players."""
        for player in self.players:
            await player.send_message(message)

class GameServer:
    def __init__(self):
        self.games: Dict[str, Game] = {}

    def generate_game_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in self.games:
                return code

    async def handle_connection(self, ws: web.WebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    if data["type"] == "create":
                        await self.handle_create_game(ws, data)
                    elif data["type"] == "join":
                        await self.handle_join_game(ws, data)
                    else:
                        game = self.find_game_for_player(ws)
                        player = self.find_player_in_game(ws, game)

                        try:
                            if data["type"] == "startGame":
                                await self.handle_start_game(game)
                            elif data["type"] == "playCard":
                                await game.play_card(player, data["card"])
                            elif data["type"] == "chooseTrump":
                                await self.handle_choose_trump(game, player, data["suit"])
                        except GameError as e:
                            await ws.send_json({"type": "error", "message": str(e)})

                elif msg.type == WSMsgType.ERROR:
                    break
                elif msg.type == WSMsgType.CLOSE:
                    break

        finally:
            await self.handle_disconnection(ws)

    async def handle_create_game(self, ws: web.WebSocketResponse, data: dict) -> None:
        code = self.generate_game_code()
        game = Game(code)
        self.games[code] = game

        player = Player(ws, data["name"], [])
        game.players.append(player)

        await ws.send_json({
            "type": "gameCreated",
            "code": code,
            "gameState": game.get_game_state(player)
        })

    async def handle_join_game(self, ws: web.WebSocketResponse, data: dict) -> None:
        code = data["code"]
        if code not in self.games:
            await ws.send_json({"type": "error", "message": "Game not found"})
            return

        game = self.games[code]
        if game.state != GameState.WAITING:
            await ws.send_json({"type": "error", "message": "Game already started"})
            return

        if len(game.players) >= 7:
            await ws.send_json({"type": "error", "message": "Game full"})
            return

        player = Player(ws, data["name"], [])
        game.players.append(player)

        await game.broadcast({
            "type": "playerJoined",
            "player": data["name"],
            "gameState": game.get_game_state()
        })

    def find_game_for_player(self, ws: web.WebSocketResponse) -> Game:
        for game in self.games.values():
            if any(p.ws == ws for p in game.players):
                return game
        raise GameError("Player not found in any game")

    def find_player_in_game(self, ws: web.WebSocketResponse, game: Game) -> Player:
        for player in game.players:
            if player.ws == ws:
                return player
        raise GameError("Player not found in game")

    async def handle_disconnection(self, ws: web.WebSocketResponse) -> None:
        try:
            game = self.find_game_for_player(ws)
            player = self.find_player_in_game(ws, game)

            game.players.remove(player)
            if not game.players:
                del self.games[game.code]
            else:
                await game.broadcast({
                    "type": "playerLeft",
                    "player": player.name,
                    "gameState": game.get_game_state()
                })
        except GameError:
            pass

    async def handle_start_game(self, game: Game) -> None:
        if game.state != GameState.WAITING:
            raise GameError("Game already started")

        if len(game.players) < 2:
            raise GameError("Need at least 2 players")

        await game.start_trump_selection()

    async def handle_choose_trump(self, game: Game, player: Player, suit: str) -> None:
        if game.state != GameState.CHOOSING_TRUMP:
            raise GameError("Not in trump choosing phase")

        if player != game.trump_chooser:
            raise GameError("Not your turn to choose trump")

        await game.handle_trump_selection(player, suit)
