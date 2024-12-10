import asyncio
import json
import random
import secrets
import string
from dataclasses import dataclass
from typing import List, Optional, Dict

from aiohttp import web, WSMsgType

from ..models.card import Card
from ..models.player import Player, HumanPlayer, AIPlayer
from ..models.trick import Trick


class GameState:
    WAITING = "waiting"
    CALLING_TRUMPS = "calling_trumps"
    PLAYING = "playing"
    FINISHED = "finished"


@dataclass
class PlayerSession:
    name: str
    game_code: str
    session_id: str
    is_spectator: bool = False

class GameError(Exception):
    pass


class Game:
    def __init__(self, code: str, on_player_eliminated=None):
        self.code = code
        self.players: List[Player] = []
        self.spectators: List[HumanPlayer] = []
        self.state = GameState.WAITING
        self.current_round = 7
        self.trump_suit: Optional[str] = None
        self.current_trick = Trick()
        self.current_player: Optional[Player] = None
        self.trick_starter: Optional[Player] = None
        self.trump_caller: Optional[Player] = None

    def next_player(self, current: Player) -> Optional[Player]:
        """Get the next player in the rotation."""
        if not self.players:
            return None
        try:
            current_idx = self.players.index(current)
            return self.players[(current_idx + 1) % len(self.players)]
        except ValueError:  # Current player not found (might have been eliminated)
            return self.players[0] if self.players else None

    async def move_to_spectator(self, player: Player) -> None:
        """Move a player to spectator status and notify them."""
        if player in self.players:
            self.players.remove(player)
            if isinstance(player, HumanPlayer):
                self.spectators.append(player)
                await player.ws.send_json({"type": "eliminated"})
                await player.ws.send_json({
                    "type": "gameState",
                    "state": self.get_game_state(),
                    "isSpectator": True
                })

    def calculate_required_decks(self) -> int:
        """Calculate how many decks are needed for the current round."""
        cards_needed = self.current_round * len(self.players)
        cards_per_deck = 52
        return max(1, (cards_needed + cards_per_deck - 1) // cards_per_deck)

    def create_deck(self) -> List[Card]:
        """Create and shuffle multiple decks of cards based on player count."""
        num_decks = self.calculate_required_decks()
        deck = []

        for _ in range(num_decks):
            deck.extend([Card(suit, rank) for suit in "♠♥♦♣" for rank in range(2, 15)])

        random.shuffle(deck)
        return deck

    async def deal_cards(self) -> None:
        """Deal cards to all players for the current round."""
        deck = self.create_deck()

        if len(deck) < (self.current_round * len(self.players)):
            raise GameError("Not enough cards in deck")

        for player in self.players:
            player.hand = [deck.pop() for _ in range(self.current_round)]
            player.sort_hand()
            player.tricks_won = 0

        await self.broadcast_game_state()

    async def reset_game(self):
        """Reset the game state for a new game."""
        self.current_round = 7
        self.trump_suit = None
        self.current_trick = Trick()
        self.current_player = None
        self.trick_starter = None
        self.trump_caller = None
        self.state = GameState.WAITING

        self.players.extend(self.spectators)
        self.spectators.clear()

        for player in self.players:
            player.hand = []
            player.tricks_won = 0

        await self.broadcast_game_state()

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all human players."""
        for player in self.players + self.spectators:
            if isinstance(player, HumanPlayer):
                await player.ws.send_json(message)

    async def broadcast_game_state(self) -> None:
        """Send current game state to all players."""
        for player in self.players + self.spectators:
            if isinstance(player, HumanPlayer):
                await player.ws.send_json(
                    {"type": "gameState", "state": self.get_game_state(player)}
                )

    async def add_ai_player(self, name: str = None) -> None:
        """Add an AI player to the game."""
        if not name:
            name = f"AI {len([p for p in self.players if isinstance(p, AIPlayer)]) + 1}"
        ai_player = AIPlayer(name)
        self.players.append(ai_player)
        await self.broadcast(
            {
                "type": "playerJoined",
                "player": ai_player.name,
                "isAI": True,
                "state": self.get_game_state(),
            }
        )

    async def handle_ai_turns(self) -> None:
        """Handle turns for AI players."""
        if self.state == GameState.CALLING_TRUMPS:
            if isinstance(self.trump_caller, AIPlayer):
                await asyncio.sleep(1)
                suit = self.trump_caller.ai.choose_trump()
                await self.handle_trump_selection(self.trump_caller, suit)

        elif self.state == GameState.PLAYING:
            while self.state == GameState.PLAYING and isinstance(
                self.current_player, AIPlayer
            ):
                await asyncio.sleep(0.5)
                ai_player = self.current_player
                card = ai_player.ai.choose_card(self.current_trick, self.trump_suit)
                await self.play_card(ai_player, str(card))

    async def start_trump_selection(self) -> None:
        """Start the trump selection phase of the round."""
        self.state = GameState.CALLING_TRUMPS
        await self.deal_cards()

        if self.current_round == 7:
            self.trump_suit = random.choice(["♠", "♥", "♦", "♣"])
            self.current_player = random.choice(self.players)
            self.trick_starter = self.current_player
            await self.start_round()
        else:
            await self.broadcast(
                {
                    "type": "trumpSelection",
                    "chooser": self.trump_caller.name,
                    "state": self.get_game_state(),
                }
            )

        await self.handle_ai_turns()

    async def start_round(self) -> None:
        """Start a new round after trump has been selected."""
        self.state = GameState.PLAYING
        self.current_trick = Trick()
        self.current_player = self.trick_starter

        await self.broadcast({"type": "roundStart", "state": self.get_game_state()})

        await self.broadcast_game_state()

    async def handle_trump_selection(self, player: Player, suit: str) -> None:
        """Handle a player's trump suit selection."""
        if self.state != GameState.CALLING_TRUMPS:
            raise GameError("Not time to call trumps")

        if player != self.trump_caller:
            raise GameError("Not your turn to call trumps")

        if suit not in "♠♥♦♣":
            raise GameError("Invalid suit")

        self.trump_suit = suit
        await self.start_round()
        await self.handle_ai_turns()

    async def handle_trick_completion(self) -> None:
        """Handle the completion of a trick."""
        await self.broadcast(
            {"type": "trickComplete", "state": self.get_game_state()}
        )

        winner = self.current_trick.determine_winner(self.trump_suit)
        winner.tricks_won += 1

        await asyncio.sleep(2)

        await self.broadcast(
            {
                "type": "trickWinner",
                "winner": winner.name,
                "state": self.get_game_state(),
            }
        )

        self.current_player = winner
        self.trick_starter = winner
        self.current_trick = Trick()

        await asyncio.sleep(1)

        if not any(len(p.hand) > 0 for p in self.players):
            await self.handle_round_end()
        else:
            await self.broadcast(
                {"type": "nextTrick", "state": self.get_game_state()}
            )

    async def handle_round_end(self) -> None:
        """Handle round end and move eliminated players to spectators."""

        eliminated_players = [p for p in self.players if p.tricks_won == 0]

        for player in eliminated_players:
            await self.move_to_spectator(player)

        if len(self.players) <= 1 or self.current_round <= 1:
            self.state = GameState.FINISHED
            if self.players:
                await self.broadcast(
                    {
                        "type": "gameOver",
                        "winner": self.players[0].name,
                        "state": self.get_game_state(),
                    }
                )
            return

        max_tricks = max(p.tricks_won for p in self.players)
        potential_choosers = [p for p in self.players if p.tricks_won == max_tricks]
        self.trump_caller = random.choice(potential_choosers)

        self.current_round -= 1
        self.trump_suit = None
        self.current_player = self.trump_caller
        self.trick_starter = self.trump_caller

        await self.broadcast(
            {
                "type": "roundEnd",
                "trumpCaller": self.trump_caller.name,
                "state": self.get_game_state(),
            }
        )

        await self.start_trump_selection()

    async def play_card(self, player: Player, card_str: str) -> None:
        """Handle a player playing a card."""
        card = Card.from_string(card_str)
        self.validate_play(player, card)

        # Play the card
        for i, c in enumerate(player.hand):
            if c.suit == card.suit and c.rank == card.rank:
                player.hand.pop(i)
                break

        self.current_trick.add_play(player, card)

        next_player = self.next_player(player)
        self.current_player = next_player

        await self.broadcast(
            {
                "type": "cardPlayed",
                "player": player.name,
                "card": card_str,
                "nextPlayer": next_player.name if next_player else None,
                "state": self.get_game_state(),
            }
        )

        if self.current_trick.is_complete(len(self.players)):
            await self.handle_trick_completion()

        await self.handle_ai_turns()

    def validate_play(self, player: Player, card: Card) -> None:
        """Prevent illegal plays."""
        if self.state != GameState.PLAYING:
            raise GameError("Not time to play")

        if player != self.current_player:
            raise GameError("Not your turn")

        if any(p == player for p, _ in self.current_trick.plays):
            raise GameError("Already played this round")

        if not any(c.suit == card.suit and c.rank == card.rank for c in player.hand):
            raise GameError("Card not in hand")

        if self.current_trick.plays and player.hand:
            if (
                any(c.suit == self.current_trick.led_suit for c in player.hand)
                and card.suit != self.current_trick.led_suit
            ):
                raise GameError("Must follow suit")

    def get_game_state(self, for_player: Optional[Player] = None) -> dict:
        """Get the current game state, optionally including player-specific information."""
        state = {
            "code": self.code,
            "currentRound": self.current_round,
            "trumpSuit": self.trump_suit,
            "currentTrick": [(p.name, str(c)) for p, c in self.current_trick.plays],
            "players": [
                {
                    "name": p.name,
                    "trickCount": p.tricks_won,
                    "isAI": isinstance(p, AIPlayer),
                }
                for p in self.players
            ],
            "spectators": [s.name for s in self.spectators],
            "state": self.state,
            "currentPlayer": (
                self.current_player.name if self.current_player and self.state == GameState.PLAYING else None
            ),
            "trumpCaller": self.trump_caller.name if self.trump_caller else None,
        }

        if for_player and for_player in self.players:
            state["hand"] = [str(c) for c in for_player.hand]

        return state

class GameServer:
    def __init__(self):
        self.games: Dict[str, Game] = {}
        self.sessions: Dict[str, PlayerSession] = {}
        self.player_ws: Dict[str, web.WebSocketResponse] = {}
        self.MAX_PLAYERS = 21

    def generate_session_id(self) -> str:
        return secrets.token_urlsafe(32)

    def create_session(self, name: str, game_code: str) -> str:
        session_id = self.generate_session_id()
        self.sessions[session_id] = PlayerSession(name=name, game_code=game_code, session_id=session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[PlayerSession]:
        return self.sessions.get(session_id)

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

                    if data.get("type") == "reconnect":
                        await self.handle_reconnection(ws, data)
                        continue

                    if data["type"] == "create":
                        await self.handle_create_game(ws, data)
                    elif data["type"] == "join":
                        await self.handle_join_game(ws, data)
                    elif data["type"] == "addAI":
                        game = self.find_game_for_player(ws)
                        await game.add_ai_player(data.get("name"))
                    else:
                        game = self.find_game_for_player(ws)
                        player = self.find_player_in_game(ws, game)

                        try:
                            if data["type"] == "startGame":
                                await self.handle_start_game(game)
                            elif data["type"] == "playCard":
                                await game.play_card(player, data["card"])
                            elif data["type"] == "callTrumps":
                                await game.handle_trump_selection(player, data["suit"])
                            elif data["type"] == "playAgain":
                                game = self.find_game_for_player(ws)
                                await game.reset_game()
                                await ws.send_json({
                                    "type": "playAgainSuccess",
                                    "state": game.get_game_state(self.find_player_in_game(ws, game))
                                })
                        except GameError as e:
                            await ws.send_json({"type": "error", "message": str(e)})

                elif msg.type == WSMsgType.ERROR:
                    break
                elif msg.type == WSMsgType.CLOSE:
                    break

        finally:
            session_id = next((sid for sid, socket in self.player_ws.items() if socket == ws), None)
            if session_id:
                del self.player_ws[session_id]

    async def handle_create_game(self, ws: web.WebSocketResponse, data: dict) -> None:
        code = self.generate_game_code()
        game = Game(code)
        self.games[code] = game

        player = HumanPlayer(ws, data["name"], [])
        session_id = self.create_session(data["name"], code)
        self.player_ws[session_id] = ws
        game.players.append(player)

        await ws.send_json(
            {
                "type": "gameCreated",
                "code": code,
                "sessionId": session_id,
                "state": game.get_game_state(player),
            }
        )

    async def handle_reconnection(self, ws: web.WebSocketResponse, data: dict) -> None:
        session_id = data.get("sessionId")
        if not session_id or session_id not in self.sessions:
            await ws.send_json({"type": "error", "message": "Invalid session"})
            return

        session = self.sessions[session_id]
        game = self.games.get(session.game_code)
        if not game:
            raise GameError("Game not found")

        self.player_ws[session_id] = ws

        # Try to find the player in both players and spectators lists
        for player in game.players:
            if isinstance(player, HumanPlayer) and player.name == session.name:
                player.ws = ws
                await ws.send_json({
                    "type": "gameState",
                    "state": game.get_game_state(player),
                    "isSpectator": False,
                    "sessionId": session_id
                })
                return

        for spectator in game.spectators:
            if isinstance(spectator, HumanPlayer) and spectator.name == session.name:
                spectator.ws = ws
                await ws.send_json({
                    "type": "gameState",
                    "state": game.get_game_state(None),
                    "isSpectator": True,
                    "sessionId": session_id
                })
                return

        raise GameError("Player not found in game")

    async def handle_join_game(self, ws: web.WebSocketResponse, data: dict) -> None:
        code = data["code"]
        if code not in self.games:
            raise GameError("Game not found")

        game = self.games[code]

        if game.state != GameState.WAITING:
            raise GameError("Game already started")
        if len(game.players) >= self.MAX_PLAYERS:
            raise GameError("Game full")

        player = HumanPlayer(ws, data["name"], [])
        session_id = self.create_session(data["name"], code)
        self.player_ws[session_id] = ws
        game.players.append(player)

        await ws.send_json({
            "type": "joined",
            "sessionId": session_id,
            "state": game.get_game_state(player)
        })

        await game.broadcast(
            {
                "type": "playerJoined",
                "player": data["name"],
                "state": game.get_game_state(),
            }
        )

    def find_game_for_player(self, ws: web.WebSocketResponse) -> Game:
        for game in self.games.values():
            if any(p.ws == ws for p in (game.players + game.spectators)):
                return game
        raise GameError("Player not found in any game")

    def find_player_in_game(self, ws: web.WebSocketResponse, game: Game) -> Player:
        for player in game.players + game.spectators:
            if player.ws == ws:
                return player
        raise GameError("Player not found in game")

    async def handle_start_game(self, game: Game) -> None:
        if game.state != GameState.WAITING:
            raise GameError("Game already started")
        if len(game.players) < 2:
            raise GameError("Need at least 2 players")
        await game.start_trump_selection()

    async def handle_choose_trump(self, game: Game, player: Player, suit: str) -> None:
        await game.handle_trump_selection(player, suit)
