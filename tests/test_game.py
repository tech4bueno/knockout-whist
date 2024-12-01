import pytest
from unittest.mock import Mock, AsyncMock

from aiohttp.web import WebSocketResponse

from knockout_whist.models.card import Card
from knockout_whist.models.player import Player
from knockout_whist.server.game_server import Game, GameState, GameError, GameServer


@pytest.fixture
def game():
    return Game("ABCD")


@pytest.fixture
def websocket():
    ws = AsyncMock(spec=WebSocketResponse)
    # Add specific aiohttp WebSocket methods
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.closed = False
    return ws


@pytest.fixture
def player(websocket):
    return Player(websocket, "TestPlayer", [])


@pytest.fixture
def game_server():
    return GameServer()


class TestGame:
    @pytest.mark.asyncio
    async def test_game_initialization(self, game):
        assert game.code == "ABCD"
        assert game.state == GameState.WAITING
        assert game.current_round == 7
        assert game.trump_suit is None
        assert len(game.players) == 0

    def test_create_deck(self, game):
        deck = game.create_deck()
        assert len(deck) == 52
        # Check all suits and ranks are present
        suits = {card.suit for card in deck}
        ranks = {card.rank for card in deck}
        assert suits == {"♠", "♥", "♦", "♣"}
        assert ranks == set(range(2, 15))

    @pytest.mark.asyncio
    async def test_deal_cards(self, game, player):
        game.players.append(player)
        await game.deal_cards()
        assert len(player.hand) == game.current_round
        player.ws.send_json.assert_called()  # Verify json was sent instead of raw message

    @pytest.mark.asyncio
    async def test_trump_selection_first_round(self, game, player):
        game.players.append(player)
        await game.start_trump_selection()
        assert game.trump_suit in ["♠", "♥", "♦", "♣"]
        assert game.state == GameState.PLAYING
        player.ws.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_trump_selection_later_rounds(self, game, player):
        game.players.append(player)
        game.current_round = 6  # Not first round
        game.trump_chooser = player
        await game.start_trump_selection()
        assert game.state == GameState.CHOOSING_TRUMP
        assert game.trump_suit is None
        player.ws.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_handle_trump_selection(self, game, player):
        game.state = GameState.CHOOSING_TRUMP
        game.players.append(player)
        game.trump_chooser = player
        await game.handle_trump_selection(player, "♠")
        assert game.trump_suit == "♠"
        assert game.state == GameState.PLAYING
        player.ws.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_trump_selection(self, game, player):
        game.state = GameState.CHOOSING_TRUMP
        game.players.append(player)
        game.trump_chooser = player
        with pytest.raises(GameError):
            await game.handle_trump_selection(player, "invalid")

    @pytest.mark.asyncio
    async def test_play_card(self, game, player):
        game.state = GameState.PLAYING
        game.players.append(player)
        player.hand = [Card("♠", 10)]
        await game.play_card(player, "10♠")
        assert len(player.hand) == 0
        player.ws.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_validate_play_wrong_turn(self, game):
        player1 = Player(AsyncMock(spec=WebSocketResponse), "Player1", [Card("♠", 10)])
        player2 = Player(AsyncMock(spec=WebSocketResponse), "Player2", [Card("♠", 9)])
        game.players.extend([player1, player2])
        game.state = GameState.PLAYING
        game.current_player_idx = 1  # Player2's turn

        with pytest.raises(GameError, match="Not your turn"):
            game.validate_play(player1, Card("♠", 10))

    @pytest.mark.asyncio
    async def test_validate_play_must_follow_suit(self, game):
        player = Player(
            AsyncMock(spec=WebSocketResponse), "Player1", [Card("♠", 10), Card("♥", 9)]
        )
        game.players.append(player)
        game.state = GameState.PLAYING
        game.current_trick.add_play(Mock(name="Previous Player"), Card("♠", 7))

        with pytest.raises(GameError, match="Must follow suit"):
            game.validate_play(player, Card("♥", 9))

    @pytest.mark.asyncio
    async def test_handle_round_end(self, game):
        player1 = Player(AsyncMock(spec=WebSocketResponse), "Player1", [])
        player2 = Player(AsyncMock(spec=WebSocketResponse), "Player2", [])
        game.players.extend([player1, player2])
        player1.tricks_won = 2
        player2.tricks_won = 1

        initial_round = game.current_round
        await game.handle_round_end()
        assert game.current_round == initial_round - 1
        assert game.trump_chooser == player1
        # Verify round end messages were sent
        player1.ws.send_json.assert_called()
        player2.ws.send_json.assert_called()


class TestGameServer:
    @pytest.mark.asyncio
    async def test_generate_game_code(self, game_server):
        code = game_server.generate_game_code()
        assert len(code) == 4
        assert code.isupper()

    @pytest.mark.asyncio
    async def test_handle_create_game(self, game_server, websocket):
        data = {"type": "create", "name": "TestPlayer"}
        await game_server.handle_create_game(websocket, data)
        assert len(game_server.games) == 1
        game = next(iter(game_server.games.values()))
        assert len(game.players) == 1
        assert game.players[0].name == "TestPlayer"
        websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_handle_join_game(self, game_server, websocket):
        # First create a game
        ws1 = AsyncMock(spec=WebSocketResponse)
        ws1.send_json = AsyncMock()
        create_data = {"type": "create", "name": "Player1"}
        await game_server.handle_create_game(ws1, create_data)
        game_code = next(iter(game_server.games.keys()))

        # Then join it
        ws2 = websocket
        join_data = {"type": "join", "code": game_code, "name": "Player2"}
        await game_server.handle_join_game(ws2, join_data)

        game = game_server.games[game_code]
        assert len(game.players) == 2
        assert game.players[1].name == "Player2"
        ws2.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_handle_join_nonexistent_game(self, game_server, websocket):
        data = {"type": "join", "code": "XXXX", "name": "TestPlayer"}
        await game_server.handle_join_game(websocket, data)
        websocket.send_json.assert_called_once()
        sent_data = websocket.send_json.call_args[0][0]
        assert sent_data["type"] == "error"
        assert sent_data["message"] == "Game not found"


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_game_flow(self, game_server):
        # Create game
        ws1 = AsyncMock(spec=WebSocketResponse)
        ws1.send_json = AsyncMock()
        await game_server.handle_create_game(ws1, {"type": "create", "name": "Player1"})
        game_code = next(iter(game_server.games.keys()))

        # Join game
        ws2 = AsyncMock(spec=WebSocketResponse)
        ws2.send_json = AsyncMock()
        await game_server.handle_join_game(
            ws2, {"type": "join", "code": game_code, "name": "Player2"}
        )

        game = game_server.games[game_code]

        # Start game
        await game_server.handle_start_game(game)
        assert game.state in [GameState.PLAYING, GameState.CHOOSING_TRUMP]

        # Verify game progression
        assert game.current_round == 7
        assert len(game.players) == 2
        for player in game.players:
            assert len(player.hand) == 7

    @pytest.mark.asyncio
    async def test_game_state_updates(self, game):
        ws1 = AsyncMock(spec=WebSocketResponse)
        ws2 = AsyncMock(spec=WebSocketResponse)
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        player1 = Player(ws1, "Player1", [])
        player2 = Player(ws2, "Player2", [])
        game.players.extend([player1, player2])

        # Test game state for different players
        state_p1 = game.get_game_state(player1)
        state_p2 = game.get_game_state(player2)

        assert state_p1["code"] == game.code
        assert state_p2["code"] == game.code
        assert len(state_p1["players"]) == 2
        assert len(state_p2["players"]) == 2
