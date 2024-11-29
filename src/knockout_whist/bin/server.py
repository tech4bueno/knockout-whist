import asyncio
import argparse
import logging
import os

from aiohttp import web
from aiohttp import WSMsgType

from ..server.game_server import GameServer

logger = logging.getLogger(__name__)


class CombinedServer:
    def __init__(self):
        self.app = web.Application()
        self.game_server = GameServer()

        self.app.router.add_get("/ws", self.websocket_handler)
        self.app.router.add_get("/", self.index_handler)
        self.app.router.add_static("/", path=self.get_static_dir())

    def get_static_dir(self):
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

    async def index_handler(self, request):
        return web.FileResponse(os.path.join(self.get_static_dir(), "index.html"))

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        logging.debug("New WebSocket connection from %s", request.remote)

        try:
            await self.game_server.handle_connection(ws)
        except Exception as e:
            raise
            logging.error("Error: %s", str(e))
        finally:
            logging.debug("WebSocket connection closed")

        return ws


async def main_async(host: str, port: int) -> None:
    server = CombinedServer()
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logging.info(f"Server running on http://{host}:{port}")

    try:
        await asyncio.Future()
    finally:
        await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Knockout Whist server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        logging.info("Server shutting down")


if __name__ == "__main__":
    main()
