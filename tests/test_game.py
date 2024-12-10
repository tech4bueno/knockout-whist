import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import WSMsgType, web
import json

from knockout_whist.models.card import Card
from knockout_whist.models.player import Player, HumanPlayer, AIPlayer
from knockout_whist.models.trick import Trick

from knockout_whist.server.game_server import Game, GameServer, GameState, GameError, PlayerSession

@pytest.fixture
def game():
    return Game("TEST1")

@pytest.fixture
def game_server():
    return GameServer()

@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws

@pytest.mark.asyncio
async def test_game_initialization(game):
    assert game.code == "TEST1"
    assert game.players == []
    assert game.spectators == []
    assert game.state == GameState.WAITING
    assert game.current_round == 7
    assert game.trump_suit is None
    assert isinstance(game.current_trick, Trick)
    assert game.current_player is None
    assert game.trick_starter is None
    assert game.trump_caller is None

@pytest.mark.asyncio
async def test_next_player(game):
    # Test with empty player list
    assert game.next_player(Mock()) is None

    # Test with single player
    player1 = Mock()
    game.players = [player1]
    assert game.next_player(player1) == player1

    # Test with multiple players
    player2 = Mock()
    player3 = Mock()
    game.players = [player1, player2, player3]
    assert game.next_player(player1) == player2
    assert game.next_player(player2) == player3
    assert game.next_player(player3) == player1

    # Test with non-existent player
    assert game.next_player(Mock()) == player1

@pytest.mark.asyncio
async def test_move_to_spectator(game, mock_ws):
    # Create a human player with mock websocket
    human_player = HumanPlayer(mock_ws, "TestPlayer", [])
    game.players = [human_player]

    await game.move_to_spectator(human_player)

    assert human_player not in game.players
    assert human_player in game.spectators
    assert len(mock_ws.send_json.mock_calls) == 2  # Should send eliminated and gameState messages

    # Verify the messages sent
    mock_ws.send_json.assert_any_call({"type": "eliminated"})
    mock_ws.send_json.assert_any_call({
        "type": "gameState",
        "state": game.get_game_state(),
        "isSpectator": True
    })

@pytest.mark.asyncio
async def test_calculate_required_decks(game):
    # Test with different numbers of players and rounds
    game.current_round = 7
    game.players = [Mock() for _ in range(3)]
    assert game.calculate_required_decks() == 1  # 21 cards needed (7 * 3)

    game.players = [Mock() for _ in range(10)]
    assert game.calculate_required_decks() == 2  # 70 cards needed (7 * 10)

    game.current_round = 1
    assert game.calculate_required_decks() == 1  # 10 cards needed (1 * 10)

@pytest.mark.asyncio
async def test_create_deck(game):
    # Test with single deck needed
    game.current_round = 7
    game.players = [Mock() for _ in range(3)]
    deck = game.create_deck()

    assert len(deck) == 52  # Standard deck size
    assert len(set(str(card) for card in deck)) == 52  # All cards unique

    # Test with multiple decks needed
    game.players = [Mock() for _ in range(10)]
    deck = game.create_deck()

    assert len(deck) == 104  # Two decks

    # Verify deck contents
    suits = set(card.suit for card in deck)
    ranks = set(card.rank for card in deck)
    assert suits == set("♠♥♦♣")
    assert ranks == set(range(2, 15))

@pytest.mark.asyncio
async def test_deal_cards(game, mock_ws):
    # Setup players
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    game.players = [player1, player2]

    await game.deal_cards()

    # Verify each player got the correct number of cards
    assert len(player1.hand) == game.current_round
    assert len(player2.hand) == game.current_round

    # Verify hands are different
    assert set(str(c) for c in player1.hand) != set(str(c) for c in player2.hand)


@pytest.mark.asyncio
async def test_reset_game(game, mock_ws):
    # Setup initial game state
    player1 = HumanPlayer(mock_ws, "Player1", [Card("♠", 10)])
    player2 = HumanPlayer(mock_ws, "Player2", [Card("♥", 10)])
    game.players = [player1]
    game.spectators = [player2]
    game.current_round = 3
    game.trump_suit = "♠"
    game.current_player = player1
    game.trick_starter = player1
    game.trump_caller = player1
    game.state = GameState.PLAYING

    await game.reset_game()

    # Verify reset state
    assert game.current_round == 7
    assert game.trump_suit is None
    assert isinstance(game.current_trick, Trick)
    assert game.current_player is None
    assert game.trick_starter is None
    assert game.trump_caller is None
    assert game.state == GameState.WAITING

    # Verify players
    assert len(game.players) == 2  # Spectator should be moved back to players
    assert len(game.spectators) == 0
    assert all(len(p.hand) == 0 for p in game.players)
    assert all(p.tricks_won == 0 for p in game.players)

@pytest.mark.asyncio
async def test_broadcast(game, mock_ws):
    # Setup players and spectators with mock websockets
    player_ws1 = AsyncMock()
    player_ws2 = AsyncMock()
    spectator_ws = AsyncMock()

    game.players = [
        HumanPlayer(player_ws1, "Player1", []),
        HumanPlayer(player_ws2, "Player2", []),
        AIPlayer("AI")  # Should not receive broadcast
    ]
    game.spectators = [HumanPlayer(spectator_ws, "Spectator", [])]

    test_message = {"type": "test", "data": "message"}
    await game.broadcast(test_message)

    # Verify broadcasts
    player_ws1.send_json.assert_called_once_with(test_message)
    player_ws2.send_json.assert_called_once_with(test_message)
    spectator_ws.send_json.assert_called_once_with(test_message)

@pytest.mark.asyncio
async def test_start_trump_selection_first_round(game, mock_ws):
    """Test trump selection for the first round (round 7)"""
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    game.players = [player1, player2]

    await game.start_trump_selection()

    assert game.state == GameState.PLAYING  # Round 7 automatically sets trump
    assert game.trump_suit in "♠♥♦♣"
    assert game.current_player in game.players
    assert game.trick_starter == game.current_player
    assert len(player1.hand) == 7
    assert len(player2.hand) == 7

@pytest.mark.asyncio
async def test_start_trump_selection_later_rounds(game, mock_ws):
    """Test trump selection for rounds after the first"""
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    game.players = [player1, player2]
    game.current_round = 6
    game.trump_caller = player1

    await game.start_trump_selection()

    assert game.state == GameState.CALLING_TRUMPS
    assert game.trump_suit is None
    mock_ws.send_json.assert_any_call({
        "type": "trumpSelection",
        "chooser": player1.name,
        "state": game.get_game_state()
    })

@pytest.mark.asyncio
async def test_handle_trump_selection(game, mock_ws):
    """Test handling of trump suit selection"""
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    game.players = [player1, player2]
    game.state = GameState.CALLING_TRUMPS
    game.trump_caller = player1

    # Test valid trump selection
    await game.handle_trump_selection(player1, "♠")
    assert game.trump_suit == "♠"
    assert game.state == GameState.PLAYING

    # Test invalid states
    game.state = GameState.PLAYING
    with pytest.raises(GameError, match="Not time to call trumps"):
        await game.handle_trump_selection(player1, "♥")

    # Test wrong player
    game.state = GameState.CALLING_TRUMPS
    with pytest.raises(GameError, match="Not your turn to call trumps"):
        await game.handle_trump_selection(player2, "♥")

    # Test invalid suit
    with pytest.raises(GameError, match="Invalid suit"):
        await game.handle_trump_selection(player1, "X")

@pytest.mark.asyncio
async def test_suit_following(game, mock_ws):
    """Test suit following requirement"""
    player1 = HumanPlayer(mock_ws, "Player1", [
        Card("♠", 10),  # 10 of spades
        Card("♥", 11)   # Jack of hearts
    ])
    game.players = [player1]
    game.state = GameState.PLAYING
    game.current_player = player1
    game.current_trick.add_play(Mock(), Card("♠", 12))

    with pytest.raises(GameError, match="Must follow suit"):
        await game.play_card(player1, "J♥")

@pytest.mark.asyncio
async def test_play_card(game, mock_ws):
    """Test playing a card during a trick"""
    player1 = HumanPlayer(mock_ws, "Player1", [Card("♠", 10), Card("♥", 11)])
    player2 = HumanPlayer(mock_ws, "Player2", [Card("♠", 12), Card("♦", 13)])
    game.players = [player1, player2]
    game.state = GameState.PLAYING
    game.current_player = player1
    game.trump_suit = "♠"

    # Test valid play
    await game.play_card(player1, "10♠")
    assert len(player1.hand) == 1
    assert len(game.current_trick.plays) == 1
    assert game.current_player == player2

    # Test following suit requirement
    await game.play_card(player2, "Q♠")

    # Test various invalid plays
    game.current_trick = Trick()
    game.current_player = player1

    # Wrong player
    with pytest.raises(GameError, match="Not your turn"):
        await game.play_card(player2, "K♦")

    # Card not in hand
    with pytest.raises(GameError, match="Card not in hand"):
        await game.play_card(player1, "7♣")

@pytest.mark.asyncio
async def test_handle_trick_completion(game, mock_ws):
    """Test handling of completed tricks"""
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    game.players = [player1, player2]
    game.trump_suit = "♠"

    # Setup a completed trick where player1 wins
    game.current_trick.add_play(player1, Card("♠", 14))  # Ace of spades
    game.current_trick.add_play(player2, Card("♠", 13))  # King of spades

    await game.handle_trick_completion()

    assert player1.tricks_won == 1
    assert player2.tricks_won == 0
    assert game.current_player == player1  # Winner leads next trick
    assert game.trick_starter == player1
    assert len(game.current_trick.plays) == 0  # New trick started

    # Verify broadcasts
    #mock_ws.send_json.assert_any_call({
    #    "type": "trickComplete",
    #    "state": game.get_game_state()
    #})
    #mock_ws.send_json.assert_any_call({
    #    "type": "trickWinner",
    #    "winner": player1.name,
    #    "state": game.get_game_state()
    #})

@pytest.mark.asyncio
async def test_handle_round_end(game, mock_ws):
    """Test handling of round end conditions"""
    player1 = HumanPlayer(mock_ws, "Player1", [])
    player2 = HumanPlayer(mock_ws, "Player2", [])
    player3 = HumanPlayer(mock_ws, "Player3", [])
    game.players = [player1, player2, player3]

    # Set up round end state
    player1.tricks_won = 3
    player2.tricks_won = 2
    player3.tricks_won = 0  # Will be eliminated

    await game.handle_round_end()

    # Verify player elimination
    assert player3 not in game.players
    assert player3 in game.spectators
    assert len(game.players) == 2

    # Verify next round setup
    assert game.current_round == 6
    assert game.trump_suit is None
    assert game.trump_caller == player1  # Won most tricks
    assert game.current_player == player1
    assert game.trick_starter == player1

@pytest.mark.asyncio
async def test_game_server_creation():
    """Test GameServer initialization"""
    server = GameServer()
    assert isinstance(server.games, dict)
    assert isinstance(server.sessions, dict)
    assert isinstance(server.player_ws, dict)
    assert server.MAX_PLAYERS == 21

@pytest.mark.asyncio
async def test_create_game(game_server, mock_ws):
    """Test game creation through GameServer"""
    create_data = {
        "type": "create",
        "name": "TestPlayer"
    }

    await game_server.handle_create_game(mock_ws, create_data)

    # Verify game creation
    assert len(game_server.games) == 1
    game_code = list(game_server.games.keys())[0]
    assert len(game_code) == 4
    assert game_code.isupper()

    # Verify player setup
    game = game_server.games[game_code]
    assert len(game.players) == 1
    assert game.players[0].name == "TestPlayer"

    # Verify session creation
    assert len(game_server.sessions) == 1
    session = list(game_server.sessions.values())[0]
    assert session.name == "TestPlayer"
    assert session.game_code == game_code

@pytest.mark.asyncio
async def test_join_game(game_server, mock_ws):
    """Test joining an existing game"""
    # Create a game first
    create_data = {"type": "create", "name": "Host"}
    await game_server.handle_create_game(mock_ws, create_data)
    game_code = list(game_server.games.keys())[0]

    # Create new websocket for joining player
    join_ws = AsyncMock()
    join_data = {
        "type": "join",
        "code": game_code,
        "name": "Joiner"
    }

    await game_server.handle_join_game(join_ws, join_data)

    # Verify game state
    game = game_server.games[game_code]
    assert len(game.players) == 2
    assert any(p.name == "Joiner" for p in game.players)

    # Test joining non-existent game
    with pytest.raises(GameError, match="Game not found"):
        await game_server.handle_join_game(join_ws, {"type": "join", "code": "XXXX", "name": "Failed"})

    # Test joining started game
    game.state = GameState.PLAYING
    with pytest.raises(GameError, match="Game already started"):
        await game_server.handle_join_game(join_ws, join_data)
