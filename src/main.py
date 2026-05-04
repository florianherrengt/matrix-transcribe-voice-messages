import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from nio import AsyncClient, LoginResponse, RoomMessageAudio, RoomMessageText

from src.config import Config
from src.matrix_client import MatrixTranscribeBot
from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


async def main():
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = Config.from_env()
    transcriber = Transcriber(config.parakeet_url)

    client = AsyncClient(
        config.homeserver,
        config.user_id,
        store_sync_tokens=True,
    )

    if config.device_id:
        client.device_id = config.device_id

    resp = await client.login(config.password)
    if not isinstance(resp, LoginResponse):
        logger.error("Login failed: %s", resp)
        sys.exit(1)

    logger.info(
        "Logged in as %s (device_id=%s)",
        config.user_id,
        client.device_id,
    )

    bot = MatrixTranscribeBot(client, transcriber)

    client.add_event_callback(bot.handle_room_message, (RoomMessageAudio, RoomMessageText))

    await client.sync(timeout=30000)

    if config.store_path:
        client.store_path = config.store_path
        await client.olm_create_account()
        await client.keys_upload()
        logger.info("E2EE keys uploaded")

    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("Bot started. Listening for voice messages...")

    while not stop_event.is_set():
        try:
            await client.sync(timeout=30000)
        except Exception:
            logger.exception("Sync error")
            await asyncio.sleep(5)

    logger.info("Shutting down...")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
