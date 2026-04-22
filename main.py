"""
Main entry point. Boots all agents inside asyncio.TaskGroup.
Each agent is shielded — a crash in one doesn't kill others.
PM2 restarts the entire process if the TaskGroup itself collapses.
"""
import asyncio
import logging

import uvicorn

from config import load_config
from db.schema import init_db
from state import SystemState, ASSETS
from agents.data_agent import run_data_agent
from agents.detection_agent import run_detection_agent
from agents.news_agent import run_news_agent
from agents.inference_manager import run_inference_manager
from agents.notification_agent import run_notification_agent
from agents.auditor_agent import run_auditor_agent
from webhooks.server import app as webhook_app, init_webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def _shielded(coro, name: str) -> None:
    """Run a coroutine in a shielded loop — log errors, never propagate."""
    while True:
        try:
            await asyncio.shield(coro)
        except asyncio.CancelledError:
            log.info(f"{name} cancelled")
            return
        except Exception as e:
            log.error(f"{name} crashed: {e}. Restarting in 10s...")
            await asyncio.sleep(10)


async def main() -> None:
    config = load_config()
    init_db()

    state = SystemState()
    inference_queue: asyncio.Queue = asyncio.Queue()
    notification_queue: asyncio.Queue = asyncio.Queue()

    init_webhook(state, notification_queue)

    log.info(f"FVG Agent starting. PAPER_MODE={config.paper_mode}")

    # Uvicorn in background thread for webhook server
    uvicorn_config = uvicorn.Config(webhook_app, host="0.0.0.0", port=8080, log_level="warning")
    server = uvicorn.Server(uvicorn_config)

    async with asyncio.TaskGroup() as tg:
        # Webhook server
        tg.create_task(_shielded(server.serve(), "WebhookServer"))

        # News agent (single, all assets)
        tg.create_task(_shielded(run_news_agent(state, config), "NewsAgent"))

        # Inference + notification (single instances)
        tg.create_task(_shielded(
            run_inference_manager(state, config, inference_queue, notification_queue),
            "InferenceManager",
        ))
        tg.create_task(_shielded(
            run_notification_agent(state, config, notification_queue),
            "NotificationAgent",
        ))

        # Auditor
        tg.create_task(_shielded(run_auditor_agent(state, config), "AuditorAgent"))

        # Per-asset agents (data + detection)
        for asset in ASSETS:
            tg.create_task(_shielded(run_data_agent(asset, state, config), f"DataAgent:{asset}"))
            tg.create_task(_shielded(
                run_detection_agent(asset, state, config, inference_queue),
                f"DetectionAgent:{asset}",
            ))


if __name__ == "__main__":
    asyncio.run(main())
