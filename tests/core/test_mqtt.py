from core.runtime.mqtt import MQTTClient


class TestMQTTClient:
    def test_topic_builder(self):
        client = MQTTClient.__new__(MQTTClient)
        assert client._device_state_topic("dev01") == "anima/devices/dev01/state"
        assert client._device_command_topic("dev01") == "anima/devices/dev01/command"
        assert client._discovery_topic() == "anima/discovery/announce"

    def test_parse_device_id_from_topic(self):
        client = MQTTClient.__new__(MQTTClient)
        assert client._parse_device_id("anima/devices/dev01/state") == "dev01"
        assert client._parse_device_id("anima/discovery/announce") is None
