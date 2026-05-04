import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from nio import AsyncClient, AsyncClientConfig, InviteEvent, LoginResponse, RoomEncryptedAudio, RoomMessageAudio, RoomMessageText

from src.config import Config
from src.cross_sign import setup_cross_signing
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
        store_path=config.store_path,
        config=AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True),
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
    logger.info("Device key fingerprint: %s", client.olm.account.identity_keys["ed25519"])

    bot = MatrixTranscribeBot(client, transcriber)

    async def auto_join(room, event):
        logger.info("Auto-joining room %s", room.room_id)
        await client.join(room.room_id)

    client.add_event_callback(auto_join, InviteEvent)
    client.add_event_callback(bot.handle_room_message, (RoomMessageAudio, RoomMessageText, RoomEncryptedAudio))

    await client.sync(timeout=30000, full_state=True)

    await client.keys_upload()
    logger.info("E2EE keys uploaded")

    if client.should_query_keys:
        await client.keys_query()
        logger.info("E2EE keys queried")

    if config.recovery_key:
        try:
            await setup_cross_signing(client, config.recovery_key)
        except Exception:
            logger.exception("Cross-signing failed")

    for user_id in client.device_store.users:
        for device in client.device_store.active_user_devices(user_id):
            if not device.verified:
                client.verify_device(device)
                logger.info("Trusted device %s for %s (startup)", device.id, user_id)

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
