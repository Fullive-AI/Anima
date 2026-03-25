from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import uvicorn

from core.api.routes import create_app
from core.brain.engine import Brain
from core.brain.skill_loader import SkillLoader
from core.cli import interactive_cli
from core.config import settings
from core.discovery import DiscoveryOrchestrator
from core.events.bus import EventBus
from core.memory.store import MemoryStore
from core.mqtt import MQTTClient
from core.rules.engine import RulesEngine
from core.scheduler.scheduler import Scheduler
from core.models import Event, EventType
from core.settings_store import SettingsStore

# Adapters
from adapters.miot.adapter import MIoTAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("anima")


class Anima:
    def __init__(self) -> None:
        # Settings store (runtime config, persisted to data/config.json)
        self.settings_store = SettingsStore(f"{settings.data_dir}/config.json")

        # Core modules
        self.bus = EventBus()
        self.mqtt = MQTTClient()
        self.memory = MemoryStore(base_dir=f"{settings.data_dir}/memory")
        self.rules = RulesEngine()
        self.skill_loader = SkillLoader(skills_dir=settings.skills_dir)
        self.brain = Brain(bus=self.bus, skill_loader=self.skill_loader, memory=self.memory)
        self.scheduler = Scheduler()

        # Adapters
        adapters = [MIoTAdapter(settings_store=self.settings_store)]
        self.discovery = DiscoveryOrchestrator(bus=self.bus, adapters=adapters)

    async def start(self, mode: str = "full") -> None:
        logger.info("Starting Anima v0.1 — Make Every Hardware Intelligent")

        # Load skills
        self.skill_loader.discover()

        # Load default rules
        self.rules.load_defaults()

        # Wire up event handlers
        self.bus.subscribe(EventType.SENSOR_UPDATED, self._on_sensor_update)

        app_state = {
            "discovery": self.discovery,
            "brain": self.brain,
            "memory": self.memory,
            "bus": self.bus,
            "settings": self.settings_store,
        }

        # Setup scheduled jobs
        self.scheduler.add_job("device_scan", self.discovery.scan, interval_seconds=300)
        self.scheduler.add_job(
            "learn_preferences",
            lambda: self.brain.learn_preferences(),
            interval_seconds=86400,  # daily
        )

        if mode == "cli":
            logger.info("Scanning for devices...")
            await self.discovery.scan()
            logger.info("Found %d device(s)", len(self.discovery.devices))
            await self._maybe_start_onboarding(app_state)

            # Run CLI mode
            scheduler_task = asyncio.create_task(self.scheduler.start())
            await interactive_cli(self.discovery, self.brain)
            self.scheduler.stop()
            scheduler_task.cancel()

        elif mode == "full":
            # Run API server + scheduler
            app = create_app(app_state)

            config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
            server = uvicorn.Server(config)

            await asyncio.gather(
                server.serve(),
                self.scheduler.start(),
                self._bootstrap_startup(app_state),
            )

    async def _bootstrap_startup(self, app_state: dict[str, object]) -> None:
        logger.info("Scanning for devices...")
        await self.discovery.scan()
        logger.info("Found %d device(s)", len(self.discovery.devices))
        await self._maybe_start_onboarding(app_state)

    async def _maybe_start_onboarding(self, app_state: dict[str, object]) -> None:
        if app_state.get("_xiaomi_qr_flow"):
            return

        if not self._has_devices_needing_token():
            logger.info("No devices waiting for token activation, skip startup onboarding")
            return

        skill = self.skill_loader.get_skill("device_discovery")
        if not skill:
            logger.warning("device_discovery skill not found, skip startup onboarding")
            return

        actions_module = self.skill_loader.load_actions(skill)
        if not actions_module or not hasattr(actions_module, "start_xiaomi_qr_scan"):
            logger.warning("device_discovery skill has no start_xiaomi_qr_scan action")
            return

        try:
            result = await actions_module.start_xiaomi_qr_scan(
                context=app_state,
                params={"country": self.settings_store.get("xiaomi_cloud_country", "cn")},
                reply="启动时已自动生成米家扫码二维码，请让用户打开米家 App 登录。",
            )
            if result.get("status") == "qr_required":
                logger.info("Startup onboarding QR generated")
            elif result.get("error"):
                logger.warning("Startup onboarding skipped: %s", result["error"])
        except Exception:
            logger.exception("Failed to auto-start startup onboarding QR flow")

    def _has_devices_needing_token(self) -> bool:
        for adapter in self.discovery._adapters:
            infos = getattr(adapter, "_device_infos", {})
            for info in infos.values():
                if info.get("needs_token"):
                    return True
        return False

    async def _on_sensor_update(self, event: Event) -> None:
        device_id = event.device_id
        if not device_id:
            return

        device = self.discovery.get_device(device_id)
        if not device:
            return

        sensor_data = event.data

        # Update cached sensor values
        self.discovery.update_device_sensors(device_id, sensor_data)

        # Fast path: rules engine
        rule_commands = await self.rules.evaluate(device.type, sensor_data, device_id)
        for cmd in rule_commands:
            await self.discovery.execute_command(cmd.device_id, cmd.action, cmd.params)

        # Slow path: LLM brain (only if rules didn't handle it)
        if not rule_commands:
            command = await self.brain.decide(device, sensor_data)
            if command:
                await self.discovery.execute_command(command.device_id, command.action, command.params)


def cli_entry():
    import argparse
    parser = argparse.ArgumentParser(description="Anima — Make Every Hardware Intelligent")
    parser.add_argument("--mode", choices=["full", "cli"], default="full",
                        help="Run mode: 'full' (API + scheduler) or 'cli' (interactive)")
    args = parser.parse_args()

    anima = Anima()
    try:
        asyncio.run(anima.start(mode=args.mode))
    except KeyboardInterrupt:
        logger.info("Anima stopped.")


if __name__ == "__main__":
    cli_entry()
