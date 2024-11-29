import asyncio
import argparse
import logging
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

from websockets.server import serve

from ..server.game_server import GameServer


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Get the static directory relative to the package
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
        super().__init__(*args, directory=static_dir, **kwargs)

    def log_message(self, format, *args):
        if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
            super().log_message(format, *args)

def run_http_server(host: str, port: int) -> None:
    """Run the HTTP server in a separate thread."""
    httpd = HTTPServer((host, port), CustomHTTPRequestHandler)
    logging.info(f"Frontend available at http://{host}:{port}")
    httpd.serve_forever()

async def main_async(
    ws_host: str,
    ws_port: int,
    http_host: str,
    http_port: int
) -> None:
    """Run both the WebSocket game server and HTTP static file server."""
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(
        target=run_http_server,
        args=(http_host, http_port),
        daemon=True
    )
    http_thread.start()

    # Start WebSocket server in the main thread
    game_server = GameServer()
    async with serve(game_server.handle_connection, ws_host, ws_port):
        logging.info(f"Game server running on ws://{ws_host}:{ws_port}")
        await asyncio.Future()  # run forever

def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Knockout Whist server")
    parser.add_argument("--ws-host", default="localhost", help="WebSocket host to bind to")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port to bind to")
    parser.add_argument("--http-host", default="localhost", help="HTTP host to bind to")
    parser.add_argument("--http-port", type=int, default=8000, help="HTTP port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        asyncio.run(main_async(
            args.ws_host,
            args.ws_port,
            args.http_host,
            args.http_port
        ))
    except KeyboardInterrupt:
        logging.info("Server shutting down")

if __name__ == "__main__":
    main()
