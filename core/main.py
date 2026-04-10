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
from core.devices.discovery import DiscoveryOrchestrator
from core.events.bus import EventBus
from core.media.audio_registry import LocalAudioRegistry
from core.media.xiaomi_speaker import XiaomiSpeakerPlayer
from core.memory.extractor import MemoryExtractionService
from core.memory.learning import PreferenceLearningService
from core.memory.store import MemoryStore
from core.rules.engine import RulesEngine
from core.runtime.cli import interactive_cli
from core.runtime.config import settings
from core.runtime.mqtt import MQTTClient
from core.runtime.settings_store import SettingsStore
from core.scheduler.scheduler import Scheduler
from core.models import Event, EventType

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
        self.memory_extractor = MemoryExtractionService(self.memory)
        self.rules = RulesEngine()
        self.skill_loader = SkillLoader(skills_dir=settings.skills_dir)
        self.brain = Brain(bus=self.bus, skill_loader=self.skill_loader, memory=self.memory)
        self.brain.set_memory_extractor(self.memory_extractor)
        self.preference_learner = PreferenceLearningService(
            self.memory,
            extractor=self.memory_extractor,
            skill_loader=self.skill_loader,
            invoke_llm_text=self.brain._invoke_llm_text,
        )
        self.brain.set_preference_learner(self.preference_learner)
        self.scheduler = Scheduler()
        self.audio_registry = LocalAudioRegistry(port=8080)
        self.speaker_player = XiaomiSpeakerPlayer(
            settings_store=self.settings_store,
            audio_registry=self.audio_registry,
            token_store_path=f"{settings.data_dir}/xiaomi_mina_token.json",
        )
        self._brain_cycle_lock = asyncio.Lock()
        self._brain_cycle_pending = False
        self._brain_cycle_task: asyncio.Task[None] | None = None

        # Adapters
        adapters = [MIoTAdapter(settings_store=self.settings_store, speaker_player=self.speaker_player)]
        self.discovery = DiscoveryOrchestrator(bus=self.bus, adapters=adapters)
        self.brain.set_environment_provider(self.discovery.get_all_devices)

    async def start(self, mode: str = "full") -> None:
        logger.info("Starting Anima v0.1 — Make Every Hardware Intelligent")

        # Load skills
        self.skill_loader.discover()

        # Wire up event handlers
        self.bus.subscribe(EventType.SENSOR_UPDATED, self._on_sensor_update)
        self.bus.subscribe(EventType.DEVICE_DISCOVERED, self._on_device_discovered)

        app_state = {
            "discovery": self.discovery,
            "brain": self.brain,
            "memory": self.memory,
            "bus": self.bus,
            "settings": self.settings_store,
            "audio_registry": self.audio_registry,
            "ensure_system_skills": self._ensure_system_skills_for_devices,
        }

        # Setup scheduled jobs
        self._register_scheduler_jobs()

        if mode == "cli":
            logger.info("Scanning for devices...")
            await self.discovery.scan()
            logger.info("Found %d device(s)", len(self.discovery.devices))
            await self._ensure_system_skills_for_devices(app_state)
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
        await self._ensure_system_skills_for_devices(app_state)
        await self._ensure_cold_start_profiles()
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

        # Queue a serialized Brain cycle so sensor refreshes can drive planning
        # without re-entering nested cycles during command verification.
        self._request_brain_cycle()

    async def _on_device_discovered(self, event: Event) -> None:
        device_id = event.device_id
        if not device_id:
            return

        device = self.discovery.get_device(device_id)
        if not device:
            return

        await self._ensure_system_skills_for_devices({
            "discovery": self.discovery,
            "brain": self.brain,
            "memory": self.memory,
            "bus": self.bus,
            "settings": self.settings_store,
        }, devices=[device])
        await self._ensure_cold_start_profiles()

    async def _ensure_system_skills_for_devices(
        self,
        app_state: dict[str, object],
        devices: list[object] | None = None,
    ) -> None:
        skill = self.skill_loader.get_skill("skill_creator")
        if not skill:
            logger.warning("skill_creator skill not found, skip system skill generation")
            return

        actions_module = self.skill_loader.load_actions(skill)
        if not actions_module or not hasattr(actions_module, "ensure_system_skills_for_devices"):
            logger.warning("skill_creator skill has no ensure_system_skills_for_devices action")
            return

        try:
            result = await actions_module.ensure_system_skills_for_devices(
                context=app_state,
                params={"devices": devices} if devices is not None else {},
                reply="",
            )
            created = result.get("created_skills", [])
            if created:
                logger.info("Auto-generated system skills: %s", ", ".join(created))
        except Exception:
            logger.exception("Failed to auto-generate missing system skills")

    def _register_scheduler_jobs(self) -> None:
        self.scheduler.add_job("device_scan", self.discovery.scan, interval_seconds=7200)
        self.scheduler.add_job(
            "environment_refresh",
            self.discovery.refresh_device_states,
            interval_seconds=60,
        )
        self.scheduler.add_job(
            "learn_preferences",
            lambda: self.preference_learner.run_now(),
            interval_seconds=300,
        )
        self.scheduler.add_job(
            "brain_tick",
            self._run_brain_cycle_serially,
            interval_seconds=60,
        )

    def _ensure_brain_cycle_state(self) -> None:
        if not hasattr(self, "_brain_cycle_lock"):
            self._brain_cycle_lock = asyncio.Lock()
        if not hasattr(self, "_brain_cycle_pending"):
            self._brain_cycle_pending = False
        if not hasattr(self, "_brain_cycle_task"):
            self._brain_cycle_task = None

    def _request_brain_cycle(self) -> None:
        self._ensure_brain_cycle_state()
        self._brain_cycle_pending = True
        task = self._brain_cycle_task
        if task is not None and not task.done():
            return
        self._brain_cycle_task = asyncio.create_task(self._drain_brain_cycles())

    async def _run_brain_cycle_serially(self) -> None:
        self._request_brain_cycle()
        task = self._brain_cycle_task
        if task is not None:
            await task

    async def _drain_brain_cycles(self) -> None:
        self._ensure_brain_cycle_state()
        async with self._brain_cycle_lock:
            while self._brain_cycle_pending:
                self._brain_cycle_pending = False
                await self.brain.run_cycle()

    async def _ensure_cold_start_profiles(self) -> None:
        device_types = [
            device.type
            for device in self.discovery.get_all_devices()
            if getattr(device, "type", "") and device.type != "unknown"
        ]
        if not device_types:
            return

        try:
            result = await self.memory.ensure_cold_start_profiles(
                device_types=device_types,
                user_id="default",
                style="comfort_first",
            )
            if result["preferences_created"] or result["profiles_created"]:
                logger.info(
                    "Cold-start context prepared: preferences_created=%s profiles_created=%s",
                    result["preferences_created"],
                    ", ".join(result["profiles_created"]) or "(none)",
                )
        except Exception:
            logger.exception("Failed to generate cold-start profiles")


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
