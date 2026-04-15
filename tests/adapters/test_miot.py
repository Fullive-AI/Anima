from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.miot.adapter import MIIO_AVAILABLE, MIoTAdapter
from core.media.xiaomi_speaker import MINA_PLAY_MUSIC_HARDWARES, XiaomiSpeakerPlayer
from core.models import Device, Sensor

_requires_miio = pytest.mark.skipif(not MIIO_AVAILABLE, reason="python-miio not installed")


class TestMIoTAdapter:
    def test_adapter_name(self):
        adapter = MIoTAdapter()
        assert adapter.name == "miot"

    @_requires_miio
    @patch("adapters.miot.adapter.miio.Discovery")
    async def test_discover_returns_devices(self, mock_discovery_cls):
        mock_info = MagicMock()
        mock_info.ip = "192.168.1.100"
        mock_info.token = "aabbccdd" * 4
        mock_info.model = "zhimi.humidifier.v1"
        mock_info.name = "Humidifier"

        adapter = MIoTAdapter()
        # Test device type mapping
        assert adapter._guess_device_type("zhimi.humidifier.v1") == "humidifier"
        assert adapter._guess_device_type("xiaomi.aircondition.mc5") == "air_conditioner"
        assert adapter._guess_device_type("yeelink.light.lamp1") == "light"
        assert adapter._guess_device_type("unknown.model.x1") == "unknown"

    def test_build_device_id(self):
        adapter = MIoTAdapter()
        did = adapter._build_device_id("192.168.1.100", "zhimi.humidifier.v1")
        assert did == "miot_192_168_1_100_zhimi_humidifier_v1"

    async def test_execute_calls_device(self):
        adapter = MIoTAdapter()
        # Without real device, execute should return failure
        result = await adapter.execute("nonexistent", "turn_on", {})
        assert result.success is False

    async def test_subscribe_refreshes_sensor_values(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_1",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[
                Sensor(name="power", unit="on/off"),
                Sensor(name="humidity", unit="%"),
                Sensor(name="water_level", unit="%"),
            ],
        )

        status = SimpleNamespace(is_on=True, humidity=48, water_level=75)
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("power").value is True
        assert device.get_sensor("humidity").value == 48
        assert device.get_sensor("water_level").value == 75

    async def test_subscribe_refreshes_air_purifier_air_quality_sensors(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_air_purifier",
            name="Air Purifier",
            adapter="miot",
            type="air_purifier",
            sensors=[
                Sensor(name="power", unit="on/off"),
                Sensor(name="pm2_5", unit="µg/m3"),
                Sensor(name="aqi", unit="AQI"),
                Sensor(name="tvoc", unit="ppb"),
                Sensor(name="co2", unit="ppm"),
                Sensor(name="temperature", unit="°C"),
                Sensor(name="humidity", unit="%"),
            ],
        )

        status = SimpleNamespace(
            is_on=True,
            pm2_5=12,
            aqi=21,
            tvoc=87,
            co2=514,
            temperature=24.6,
            humidity=46,
        )
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("power").value is True
        assert device.get_sensor("pm2_5").value == 12
        assert device.get_sensor("aqi").value == 21
        assert device.get_sensor("tvoc").value == 87
        assert device.get_sensor("co2").value == 514
        assert device.get_sensor("temperature").value == 24.6
        assert device.get_sensor("humidity").value == 46

    async def test_subscribe_maps_aqi_to_pm25_when_pm25_field_is_missing(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_air_purifier",
            name="Air Purifier",
            adapter="miot",
            type="air_purifier",
            sensors=[
                Sensor(name="pm2_5", unit="µg/m3"),
                Sensor(name="aqi", unit="AQI"),
            ],
        )

        status = SimpleNamespace(aqi=9)
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("aqi").value == 9
        assert device.get_sensor("pm2_5").value == 9

    @_requires_miio
    def test_unknown_model_gets_generic_reflection_capabilities(self):
        adapter = MIoTAdapter()

        capabilities = adapter._build_capabilities("unknown.vendor.device", has_token=True)
        capability_names = {capability.name for capability in capabilities}

        assert capability_names == {
            "miot_get_property",
            "miot_set_property",
            "miot_call_action",
        }

    def test_wifispeaker_capabilities_include_audio_playback(self):
        adapter = MIoTAdapter()

        capabilities = adapter._build_capabilities("xiaomi.wifispeaker.oh2", has_token=True)
        capability_names = {capability.name for capability in capabilities}

        assert {"play_audio_file", "play_audio_url", "play_random_audio", "stop_audio"} <= capability_names

    async def test_execute_play_audio_file_uses_speaker_player(self):
        speaker_player = AsyncMock()
        speaker_player.play_file.return_value = {
            "url": "http://127.0.0.1:8080/api/audio/token",
            "status": {"data": {"info": '{"status":1}'}},
        }
        adapter = MIoTAdapter(speaker_player=speaker_player)
        adapter._device_infos["speaker_01"] = {
            "ip": "192.168.1.10",
            "did": "2039812956",
            "model": "xiaomi.wifispeaker.oh2",
        }

        result = await adapter.execute("speaker_01", "play_audio_file", {"path": "/tmp/test.wav"})

        assert result.success is True
        assert "http://127.0.0.1:8080/api/audio/token" in result.message
        speaker_player.play_file.assert_awaited_once()

    async def test_execute_play_random_audio_uses_speaker_player(self):
        speaker_player = AsyncMock()
        speaker_player.play_random_file.return_value = {
            "path": "/tmp/library/song.wav",
            "url": "http://127.0.0.1:8080/api/audio/token",
            "status": {"data": {"info": '{"status":1}'}},
        }
        adapter = MIoTAdapter(speaker_player=speaker_player)
        adapter._device_infos["speaker_01"] = {
            "ip": "192.168.1.10",
            "did": "2039812956",
            "model": "xiaomi.wifispeaker.oh2",
        }

        result = await adapter.execute("speaker_01", "play_random_audio", {})

        assert result.success is True
        assert result.message == "/tmp/library/song.wav"
        speaker_player.play_random_file.assert_awaited_once()

    @_requires_miio
    async def test_load_cached_cloud_devices_without_relogin(self):
        class FakeSettings:
            def get(self, key, default=None):
                if key == "xiaomi_cloud_devices":
                    return [
                        {
                            "name": "Xiaomi Smart Speaker",
                            "model": "xiaomi.wifispeaker.oh2",
                            "did": "2039812956",
                            "localip": "192.168.110.147",
                            "token": "4a65af10e97391301c7d618d3770d41e",
                            "isOnline": True,
                        }
                    ]
                return default

            def get_xiaomi_credentials(self):
                return None

            def get_xiaomi_country(self):
                return "cn"

        adapter = MIoTAdapter(settings_store=FakeSettings())

        with (
            patch.object(adapter, "_load_manual_devices", return_value=[]),
            patch.object(
                adapter,
                "_discover_cloud",
                return_value=[],
            ),
            patch.object(adapter, "_discover_local", return_value=[]),
        ):
            devices = await adapter.discover()

        assert len(devices) == 1
        assert devices[0].type == "speaker"
        assert devices[0].device_id == "miot_cloud_2039812956"
        assert any(cap.name == "play_audio_file" for cap in devices[0].capabilities)

    def test_speaker_player_coerces_numeric_credentials(self):
        class FakeSettings:
            def get_xiaomi_credentials(self):
                return 13800138000, 123456

        player = XiaomiSpeakerPlayer(
            settings_store=FakeSettings(),
            audio_registry=MagicMock(),
            token_store_path="/tmp/anima-xiaomi-token-test.json",
        )

        assert player._get_credentials() == ("13800138000", "123456")

    def test_oh2_uses_play_music_api_path(self):
        assert "OH2" in MINA_PLAY_MUSIC_HARDWARES

    async def test_speaker_player_random_file_prefers_audio_library_dir(self, tmp_path):
        library = tmp_path / "library"
        library.mkdir()
        song = library / "song.wav"
        song.write_bytes(b"RIFFdemoWAVE")

        class FakeSettings:
            def get_xiaomi_credentials(self):
                return "user", "pass"

            def get_audio_library_dir(self):
                return str(library)

        player = XiaomiSpeakerPlayer(
            settings_store=FakeSettings(),
            audio_registry=MagicMock(),
            token_store_path=str(tmp_path / "token.json"),
        )
        player.play_file = AsyncMock(return_value={"url": "http://x", "status": {}, "path": str(song)})

        result = await player.play_random_file({"ip": "192.168.1.10"})

        assert result["path"] == str(song)
        player.play_file.assert_awaited_once()

    async def test_speaker_player_stop_waits_for_stopped_state(self, tmp_path):
        class FakeSettings:
            def get_xiaomi_credentials(self):
                return "user", "pass"

        player = XiaomiSpeakerPlayer(
            settings_store=FakeSettings(),
            audio_registry=MagicMock(),
            token_store_path=str(tmp_path / "token.json"),
        )

        class FakeAccount:
            async def close(self):
                return None

        class FakeService:
            def __init__(self):
                self.calls = 0

            async def stop(self, *, device_id):
                return {"code": 0}

            async def player_status(self, *, device_id):
                self.calls += 1
                state = 1 if self.calls == 1 else 2
                return {"data": {"info": f'{{"status":{state}}}'}}

        fake_service = FakeService()
        player._resolve_mina_device = AsyncMock(return_value=(FakeAccount(), fake_service, {"deviceID": "mina_dev_01"}))

        status = await player.stop({"did": "2039812956"})

        assert player._extract_player_state(status) == 2

    async def test_subscribe_refreshes_generic_device_status(self):
        adapter = MIoTAdapter()
        device = Device(
            device_id="miot_generic",
            name="Unknown Device",
            adapter="miot",
            type="unknown",
            sensors=[
                Sensor(name="power", unit="on/off"),
                Sensor(name="miot_online", unit="bool"),
            ],
        )

        status = SimpleNamespace(power="on")
        miio_device = SimpleNamespace(status=lambda: status)

        with patch.object(adapter, "_get_miio_device", return_value=miio_device):
            await adapter.subscribe(device)

        assert device.get_sensor("power").value is True
        assert device.get_sensor("miot_online").value is True
