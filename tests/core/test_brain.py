from unittest.mock import AsyncMock, patch

from core.brain.engine import Brain
from core.brain.skill_loader import SkillLoader
from core.models import (
    Capability,
    Device,
    DeviceCommand,
    Sensor,
    SkillActionSpec,
    SkillSummary,
    TaskPlanItem,
)
from skills.system.air_purifier.scripts.actions import execute as execute_air_purifier_skill
from skills.system.speaker.scripts.actions import execute as execute_speaker_skill


class TestBrain:
    def test_build_context(self):
        brain = Brain.__new__(Brain)
        brain._skill_loader = SkillLoader(skills_dir="skills")
        brain._skill_loader.discover()
        brain._environment_provider = None

        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=35)],
        )

        skill = brain._skill_loader.get_skill_for_device("humidifier")
        context = brain._build_prompt_context(
            skill=skill,
            device=device,
            user_memory={
                "preferences": "likes 55%",
                "history": [],
                "learned": "",
                "learned_profiles": {"humidifier": '{"stable_preferences":["55% humidity"]}'},
            },
            planner_goal="raise humidity",
            planner_reason="room is dry",
        )
        assert "humidity" in context.lower()
        assert "35" in context
        assert "55% humidity" in context
        assert "current environment state" in context.lower()
        assert "planner intent" in context.lower()

    def test_get_environment_state(self):
        brain = Brain.__new__(Brain)
        current_device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=35)],
        )
        peer_device = Device(
            device_id="ac_01",
            name="AC",
            adapter="miot",
            type="air_conditioner",
            sensors=[Sensor(name="temperature", unit="°C", value=27)],
        )
        brain._environment_provider = lambda: [current_device, peer_device]

        snapshot = brain.get_environment_state()

        assert snapshot["current_device_id"] is None
        assert len(snapshot["devices"]) == 2
        assert "humidity" in snapshot["signals"]
        assert "temperature" in snapshot["signals"]

    def test_parse_llm_response_valid_json(self):
        brain = Brain.__new__(Brain)
        response = '{"action": "set_humidity", "params": {"value": 55}, "reason": "too dry", "confidence": 0.91, "expected_outcome": "raise humidity", "should_wait_seconds": 900}'
        result = brain._parse_llm_response(response, "hum_01")
        assert result is not None
        assert result.action == "set_humidity"
        assert result.params["value"] == 55
        assert result.confidence == 0.91
        assert result.expected_outcome == "raise humidity"
        assert result.should_wait_seconds == 900

    def test_parse_planner_response_fills_device_type(self):
        brain = Brain.__new__(Brain)
        response = '[{"skill_name":"humidifier","goal":"raise humidity","reason":"dry","priority":5}]'
        result = brain._parse_planner_response(
            response,
            [SkillSummary(name="humidifier", description="skill", device_type="humidifier")],
        )
        assert len(result) == 1
        assert result[0].skill_name == "humidifier"
        assert result[0].device_type == "humidifier"
        assert result[0].priority == 5

    def test_parse_cycle_plan_supports_task_plan_items(self):
        brain = Brain.__new__(Brain)
        tasks, plan_items = brain._parse_cycle_plan(
            '{"task_plan_items":[{"kind":"refresh_environment","reason":"need latest state","priority":5},{"kind":"execute_skill","skill_name":"humidifier","goal":"raise humidity","reason":"dry","priority":10}]}',
            [SkillSummary(name="humidifier", description="skill", device_type="humidifier")],
        )

        assert len(tasks) == 2
        assert tasks[0].kind == "refresh_environment"
        assert tasks[1].kind == "execute_skill"
        assert len(plan_items) == 1
        assert plan_items[0].skill_name == "humidifier"

    def test_parse_cycle_plan_legacy_list_remains_compatible(self):
        brain = Brain.__new__(Brain)
        tasks, plan_items = brain._parse_cycle_plan(
            '[{"skill_name":"humidifier","goal":"raise humidity","reason":"dry","priority":5}]',
            [SkillSummary(name="humidifier", description="skill", device_type="humidifier")],
        )

        assert len(tasks) == 1
        assert tasks[0].kind == "execute_skill"
        assert len(plan_items) == 1
        assert plan_items[0].skill_name == "humidifier"

    def test_build_planner_prompt_includes_humidifier_threshold_hint(self):
        brain = Brain.__new__(Brain)
        prompt = brain._build_planner_prompt(
            devices=[],
            environment_state={},
            user_memory={},
            lightweight_skills=[
                SkillSummary(name="humidifier", description="humidity control", device_type="humidifier")
            ],
        )
        assert "below 50%" in prompt
        assert "humidifier" in prompt

    def test_load_planner_hints_from_markdown_file(self):
        brain = Brain.__new__(Brain)
        hints = brain._load_planner_hints()
        assert "# Planner Hints" in hints
        assert "below 50%" in hints

    def test_build_chat_planner_prompt_includes_system_action_schema(self):
        brain = Brain.__new__(Brain)
        prompt = brain._build_chat_planner_prompt(
            message="帮我扫描设备",
            devices=[],
            environment_state={},
            user_memory={},
            skill_summaries=[SkillSummary(name="device_discovery", description="scan devices", device_type="")],
        )
        assert "task_plan_items" in prompt
        assert "scan_local_devices" in prompt
        assert "ask_user" in prompt

    def test_detects_explicit_skill_creation_intent(self):
        brain = Brain.__new__(Brain)
        assert brain._looks_like_skill_creation_request("帮我新增一个起床提醒技能") is True
        assert brain._looks_like_skill_creation_request("create a custom skill to close curtains at night") is True

    def test_does_not_treat_environment_query_as_skill_creation_intent(self):
        brain = Brain.__new__(Brain)
        assert brain._looks_like_skill_creation_request("现在屋内的状态") is False
        assert brain._looks_like_skill_creation_request("帮我看看现在房间温度和湿度") is False

    def test_parse_chat_plan_supports_task_plan_items(self):
        brain = Brain.__new__(Brain)
        plan = brain._parse_chat_plan(
            '{"reply":"我先确认一下。","should_execute":true,"task_plan_items":[{"kind":"ask_user","question":"你想调节哪个房间？","reason":"scope ambiguous","priority":5},{"kind":"execute_skill","skill_name":"humidifier","goal":"raise humidity","reason":"room is dry","priority":10}]}',
            [SkillSummary(name="humidifier", description="skill", device_type="humidifier")],
        )

        assert plan.should_execute is True
        assert len(plan.task_plan_items) == 2
        assert plan.task_plan_items[0].kind == "ask_user"
        assert plan.task_plan_items[0].question == "你想调节哪个房间？"
        assert plan.task_plan_items[1].kind == "execute_skill"
        assert plan.task_plan_items[1].skill_name == "humidifier"

    def test_normalize_chat_tasks_preserves_new_task_items(self):
        brain = Brain.__new__(Brain)
        task = TaskPlanItem(kind="ask_user", question="请确认目标房间", priority=5)
        tasks = brain._normalize_chat_tasks(
            type(
                "Plan",
                (),
                {
                    "task_plan_items": [task],
                    "system_action": "none",
                    "system_skill": "",
                    "params": {},
                    "skill_plan_items": [],
                },
            )()
        )
        assert tasks == [task]

    def test_sanitize_command_with_capability_limits(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="miot",
            type="humidifier",
            capabilities=[
                Capability(name="set_humidity", params={"min": 30, "max": 80, "step": 5}),
            ],
        )
        command = DeviceCommand(device_id="hum_01", action="set_humidity", params={"value": 83})
        result = brain._sanitize_command_for_device(command, device)
        assert result is not None
        assert result.params["value"] == 80

    def test_derive_expected_state(self):
        brain = Brain.__new__(Brain)
        command = DeviceCommand(device_id="light_01", action="set_brightness", params={"value": 60})
        expected = brain._derive_expected_state(command)
        assert expected == {"brightness": 60}

    async def test_execute_action_with_retry_verifies_state(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="light_01",
            name="Light",
            adapter="fake",
            type="light",
            sensors=[Sensor(name="power", unit="on/off", value=False)],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.calls = 0

            async def execute_command(self, device_id, action, params):
                self.calls += 1
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                self.target.get_sensor("power").value = True
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target

        discovery = FakeDiscovery(device)
        action_spec = SkillActionSpec(
            skill_name="light",
            device_id="light_01",
            action="turn_on",
            params={},
            expected_state={"power": True},
        )

        verification = await brain._execute_action_with_retry(action_spec, discovery)

        assert verification.verified is True
        assert verification.status == "verified"
        assert verification.attempts == 1

    async def test_execute_action_with_retry_treats_missing_expected_sensor_as_unverifiable(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="hum_01",
            name="Humidifier",
            adapter="fake",
            type="humidifier",
            sensors=[Sensor(name="humidity", unit="%", value=43)],
        )

        class FakeDiscovery:
            async def execute_command(self, device_id, action, params):
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return device

        verification = await brain._execute_action_with_retry(
            SkillActionSpec(
                skill_name="humidifier",
                device_id="hum_01",
                action="set_humidity",
                params={"value": 50},
                expected_state={"target_humidity": 50},
            ),
            FakeDiscovery(),
        )

        assert verification.verified is True
        assert verification.status == "unverifiable_but_executed"
        assert verification.attempts == 1
        assert verification.observed_state == {"target_humidity": None}

    async def test_execute_action_with_retry_does_not_treat_failed_command_as_success(self):
        brain = Brain.__new__(Brain)
        device = Device(
            device_id="speaker_01",
            name="Speaker",
            adapter="fake",
            type="speaker",
            sensors=[],
        )

        class FakeDiscovery:
            async def execute_command(self, device_id, action, params):
                return type("Result", (), {"message": "speaker rejected request", "success": False})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return device

        verification = await brain._execute_action_with_retry(
            SkillActionSpec(
                skill_name="speaker",
                device_id="speaker_01",
                action="play_random_audio",
                params={},
                expected_state={},
            ),
            FakeDiscovery(),
        )

        assert verification.verified is False
        assert verification.status == "verification_failed"
        assert verification.message == "speaker rejected request"

    async def test_air_purifier_execute_maps_turn_off_intent_to_off_action(self):
        purifier = Device(
            device_id="purifier_01",
            name="Purifier",
            adapter="fake",
            type="air_purifier",
            online=True,
            capabilities=[Capability(name="on"), Capability(name="off")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                assert device_type == "air_purifier"
                return [purifier]

        actions = await execute_air_purifier_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type(
                "PlanItem",
                (),
                {
                    "goal": "turn off the air purifier",
                    "reason": "用户要求关闭空气净化器",
                },
            )(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "off"
        assert actions[0]["expected_state"] == {"power": False}

    async def test_air_purifier_execute_maps_chinese_off_intent(self):
        purifier = Device(
            device_id="purifier_01",
            name="空气净化器",
            adapter="fake",
            type="air_purifier",
            online=True,
            capabilities=[Capability(name="on"), Capability(name="off")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                return [purifier]

        actions = await execute_air_purifier_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type("PlanItem", (), {"goal": "关闭空气净化器", "reason": "空气质量已恢复"})(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "off"
        assert actions[0]["expected_state"] == {"power": False}

    async def test_air_purifier_execute_maps_chinese_on_intent(self):
        purifier = Device(
            device_id="purifier_01",
            name="空气净化器",
            adapter="fake",
            type="air_purifier",
            online=True,
            capabilities=[Capability(name="on"), Capability(name="off")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                return [purifier]

        actions = await execute_air_purifier_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type("PlanItem", (), {"goal": "打开空气净化器", "reason": "空气不太好"})(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "on"
        assert actions[0]["expected_state"] == {"power": True}

    async def test_speaker_execute_maps_chinese_stop_intent(self):
        speaker = Device(
            device_id="speaker_01",
            name="智能音箱",
            adapter="fake",
            type="speaker",
            online=True,
            capabilities=[Capability(name="play_random_audio"), Capability(name="stop_audio")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                return [speaker]

        actions = await execute_speaker_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type("PlanItem", (), {"goal": "停止播放音乐", "reason": "用户要求暂停"})(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "stop_audio"

    async def test_speaker_execute_maps_chinese_play_intent(self):
        speaker = Device(
            device_id="speaker_01",
            name="智能音箱",
            adapter="fake",
            type="speaker",
            online=True,
            capabilities=[Capability(name="play_random_audio"), Capability(name="stop_audio")],
        )

        class FakeDiscovery:
            def get_devices_by_type(self, device_type):
                return [speaker]

        actions = await execute_speaker_skill(
            context={"discovery": FakeDiscovery(), "brain": object()},
            plan_item=type("PlanItem", (), {"goal": "来一首歌曲", "reason": "用户想听音乐"})(),
        )

        assert len(actions) == 1
        assert actions[0]["action"] == "play_random_audio"

    def test_build_deterministic_cycle_tasks_bootstraps_air_purifier_on_startup(self):
        brain = Brain.__new__(Brain)
        brain._air_purifier_startup_bootstrap_pending = True
        purifier = Device(
            device_id="purifier_01",
            name="Purifier",
            adapter="fake",
            type="air_purifier",
            sensors=[Sensor(name="power", unit="on/off", value=False)],
        )

        tasks = brain._build_deterministic_cycle_tasks(
            devices=[purifier],
            lightweight_skills=[SkillSummary(name="air_purifier", description="purifier", device_type="air_purifier")],
        )

        assert len(tasks) == 1
        assert tasks[0].kind == "execute_skill"
        assert tasks[0].skill_name == "air_purifier"
        assert "开启" in tasks[0].goal

    def test_build_deterministic_cycle_tasks_turns_off_purifier_when_aqi_is_low(self):
        brain = Brain.__new__(Brain)
        brain._air_purifier_startup_bootstrap_pending = False
        purifier = Device(
            device_id="purifier_01",
            name="Purifier",
            adapter="fake",
            type="air_purifier",
            sensors=[
                Sensor(name="power", unit="on/off", value=True),
                Sensor(name="aqi", unit="AQI", value=3),
            ],
        )

        tasks = brain._build_deterministic_cycle_tasks(
            devices=[purifier],
            lightweight_skills=[SkillSummary(name="air_purifier", description="purifier", device_type="air_purifier")],
        )

        assert len(tasks) == 1
        assert tasks[0].skill_name == "air_purifier"
        assert "关闭" in tasks[0].goal

    def test_build_deterministic_cycle_tasks_uses_average_aqi_when_aqi_missing(self):
        brain = Brain.__new__(Brain)
        brain._air_purifier_startup_bootstrap_pending = False
        purifier = Device(
            device_id="purifier_01",
            name="Purifier",
            adapter="fake",
            type="air_purifier",
            sensors=[
                Sensor(name="power", unit="on/off", value=False),
                Sensor(name="average_aqi", unit="AQI", value=8),
            ],
        )

        tasks = brain._build_deterministic_cycle_tasks(
            devices=[purifier],
            lightweight_skills=[SkillSummary(name="air_purifier", description="purifier", device_type="air_purifier")],
        )

        assert len(tasks) == 1
        assert tasks[0].skill_name == "air_purifier"
        assert "开启" in tasks[0].goal

    async def test_handle_chat_message_routes_device_discovery_before_unified_planner(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def __init__(self):
                self.devices = {}

            def get_all_devices(self):
                return []

            def get_devices_by_type(self, device_type):
                return []

            async def scan(self):
                self.devices["dev1"] = Device(
                    device_id="dev1",
                    name="Lamp",
                    adapter="fake",
                    type="light",
                )
                return [self.devices["dev1"]]

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            return_value='{"action":"scan_local_devices","params":{},"reply":"我先扫描一下当前设备。"}'
        )

        result = await brain.handle_chat_message(
            "帮我扫描设备",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["action"] == "scan_local_devices"
        assert result["new_devices"] == 1
        assert brain._invoke_llm_text.await_count == 1

    async def test_handle_chat_message_routes_skill_creation_before_unified_planner(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def get_all_devices(self):
                return []

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            return_value='{"action":"create_custom_skill","params":{"request":"新增一个控制窗帘的技能"},"reply":"我来创建这个技能。"}'
        )
        skill = loader.get_skill("skill_creator")
        assert skill is not None
        actions_module = loader.load_actions(skill)
        assert actions_module is not None

        with patch.object(
            actions_module,
            "create_custom_skill",
            AsyncMock(
                return_value={
                    "reply": "已创建",
                    "action": "create_custom_skill",
                    "status": "created",
                    "folder_name": "curtain",
                }
            ),
        ) as create_mock:
            result = await brain.handle_chat_message(
                "帮我新增一个控制窗帘的技能",
                {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
            )

        assert result["action"] == "create_custom_skill"
        assert result["status"] == "created"
        assert brain._invoke_llm_text.await_count == 1
        assert create_mock.await_count == 1

    async def test_handle_chat_message_does_not_route_environment_query_to_skill_creator(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def get_all_devices(self):
                return []

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 0, "failed": 0}

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            side_effect=[
                '{"action":"none","params":{},"reply":""}',
                '{"reply":"当前没有可读取的室内环境数据。","should_execute":false,"task_plan_items":[]}',
            ]
        )

        skill = loader.get_skill("skill_creator")
        assert skill is not None
        actions_module = loader.load_actions(skill)
        assert actions_module is not None

        with patch.object(actions_module, "create_custom_skill", AsyncMock()) as create_mock:
            result = await brain.handle_chat_message(
                "现在屋内的状态",
                {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
            )

        assert result["reply"] == "当前没有可读取的室内环境数据。"
        assert "action" not in result or result.get("action") != "create_custom_skill"
        assert brain._invoke_llm_text.await_count == 2
        assert create_mock.await_count == 0

    async def test_handle_chat_message_resumes_pending_skill_creation_after_clarification(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def get_all_devices(self):
                return []

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            return_value='{"action":"create_custom_skill","params":{"request":"新增一个起床提醒技能"},"reply":"我来创建这个技能。"}'
        )
        skill = loader.get_skill("skill_creator")
        assert skill is not None
        actions_module = loader.load_actions(skill)
        assert actions_module is not None

        create_mock = AsyncMock(
            side_effect=[
                {
                    "reply": "我需要先确认几件事，避免生成一个过于宽泛的 skill：\n1. What specific time do you want to be woken up on weekdays?",
                    "action": "create_custom_skill",
                    "status": "needs_clarification",
                    "questions": ["What specific time do you want to be woken up on weekdays?"],
                },
                {
                    "reply": "已创建",
                    "action": "create_custom_skill",
                    "status": "created",
                    "folder_name": "wake_up_reminder",
                },
            ]
        )

        with patch.object(actions_module, "create_custom_skill", create_mock):
            first = await brain.handle_chat_message(
                "新增一个起床提醒技能",
                {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
            )
            second = await brain.handle_chat_message(
                "工作日早上 7:30 叫我起床，法定节假日不提醒",
                {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
            )

        assert first["status"] == "needs_clarification"
        assert second["status"] == "created"
        assert brain._invoke_llm_text.await_count == 1
        assert create_mock.await_count == 2
        second_request = create_mock.await_args_list[1].kwargs["params"]["request"]
        assert create_mock.await_args_list[1].kwargs["params"]["allow_clarification"] is False
        assert "新增一个起床提醒技能" in second_request
        assert "工作日早上 7:30 叫我起床" in second_request
        assert brain._pending_skill_creation is None

    async def test_handle_chat_message_can_cancel_pending_skill_creation(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)
        brain._pending_skill_creation = {
            "request": "新增一个起床提醒技能",
            "questions": ["What specific time do you want to be woken up on weekdays?"],
        }

        result = await brain.handle_chat_message(
            "算了，先取消",
            {
                "discovery": object(),
                "settings": type(
                    "Settings",
                    (),
                    {"get": lambda self, key, default=None: "sk-test" if key == "llm_api_key" else default},
                )(),
                "brain": brain,
            },
        )

        assert result["reply"] == "已取消上一次技能创建请求。"
        assert brain._pending_skill_creation is None

    async def test_handle_chat_message_runs_speaker_skill_for_random_playback(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        speaker = Device(
            device_id="speaker_01",
            name="Xiaomi Smart Speaker",
            adapter="miot",
            type="speaker",
            capabilities=[Capability(name="play_random_audio"), Capability(name="stop_audio")],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []

            def get_all_devices(self):
                return [self.target]

            def get_devices_by_type(self, device_type):
                return [self.target] if device_type == "speaker" else []

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery(speaker)
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value='{"reply":"我来随机放一首。","should_execute":true,"system_action":"none","system_skill":"","params":{},"skill_plan_items":[{"skill_name":"speaker","goal":"play random music on the speaker","reason":"user asked to play music","priority":10}]}'
        )

        result = await brain.handle_chat_message(
            "随机放一首歌",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["executed"] is True
        assert result["execution_results"][0]["actions"][0]["action"] == "play_random_audio"
        assert discovery.executed == [("speaker_01", "play_random_audio", {})]

    async def test_handle_chat_message_returns_question_for_ask_user_task(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def get_all_devices(self):
                return []

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value='{"reply":"我先确认一下房间。","should_execute":true,"task_plan_items":[{"kind":"ask_user","question":"你想调节哪个房间？","reason":"scope ambiguous","priority":5}]}'
        )

        result = await brain.handle_chat_message(
            "帮我调节一下湿度",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["executed"] is False
        assert result["reply"] == "你想调节哪个房间？"
        assert result["task_results"][0]["kind"] == "ask_user"

    async def test_handle_chat_message_can_execute_custom_skill(self, tmp_path):
        skills_dir = tmp_path / "skills"
        custom_skill_dir = skills_dir / "custom" / "night_curtain"
        references_dir = custom_skill_dir / "references"
        scripts_dir = custom_skill_dir / "scripts"
        references_dir.mkdir(parents=True)
        scripts_dir.mkdir()

        (custom_skill_dir / "SKILL.md").write_text(
            (
                "---\n"
                "name: night_curtain\n"
                "description: open curtains when the user asks\n"
                "metadata:\n"
                "  device_types:\n"
                "    - curtain\n"
                "---\n\n"
                "# Night Curtain\n"
            ),
            encoding="utf-8",
        )
        (references_dir / "knowledge.md").write_text("Curtains support open and close actions.", encoding="utf-8")
        (references_dir / "decide.md").write_text(
            (
                "Use {current_data}, {capabilities}, {user_preferences}, {learned_profile}, "
                "{recent_history}, and {knowledge} to decide whether to return `none` or an action."
            ),
            encoding="utf-8",
        )
        (scripts_dir / "actions.py").write_text(
            (
                "from core.models import DeviceCommand\n\n"
                'def open(device_id: str, reason: str = "") -> DeviceCommand:\n'
                '    return DeviceCommand(device_id=device_id, action="open", source="brain", reason=reason)\n'
            ),
            encoding="utf-8",
        )

        loader = SkillLoader(skills_dir=str(skills_dir))
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        curtain = Device(
            device_id="curtain_01",
            name="Bedroom Curtain",
            adapter="fake",
            type="curtain",
            capabilities=[Capability(name="open"), Capability(name="close")],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []

            def get_all_devices(self):
                return [self.target]

            def get_devices_by_type(self, device_type):
                return [self.target] if device_type == "curtain" else []

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery(curtain)
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            side_effect=[
                '{"reply":"我来开窗帘。","should_execute":true,"task_plan_items":[{"kind":"execute_skill","skill_name":"night_curtain","goal":"open the curtain","reason":"user asked to open the curtain","priority":10}]}',
                '{"action":"open","params":{},"reason":"user asked to open the curtain"}',
            ]
        )

        result = await brain.handle_chat_message(
            "打开窗帘",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["executed"] is True
        assert result["execution_results"][0]["plan_item"]["skill_name"] == "night_curtain"
        assert result["execution_results"][0]["actions"][0]["action"] == "open"
        assert discovery.executed == [("curtain_01", "open", {})]

    async def test_handle_chat_message_maps_legacy_skill_creator_action_alias(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        class FakeDiscovery:
            def get_all_devices(self):
                return []

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery()
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = AsyncMock(
            return_value='{"reply":"我来创建一个新技能。","should_execute":true,"task_plan_items":[{"kind":"system_action","system_skill":"skill_creator","system_action":"generate_new_skill_package","params":{"request":"新增一个控制窗帘的技能"},"reason":"user asked to create a new skill","priority":10}]}'
        )
        skill = loader.get_skill("skill_creator")
        assert skill is not None
        actions_module = loader.load_actions(skill)
        assert actions_module is not None

        with patch.object(
            actions_module,
            "create_custom_skill",
            AsyncMock(return_value={"reply": "已创建", "action": "create_custom_skill", "status": "created"}),
        ):
            result = await brain.handle_chat_message(
                "帮我新增一个控制窗帘的技能",
                {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
            )

        assert result["action"] == "create_custom_skill"
        assert result["requested_action"] == "generate_new_skill_package"

    async def test_handle_chat_message_refreshes_environment_before_running_skill(self, tmp_path):
        loader = SkillLoader(skills_dir="skills")
        loader.discover()
        memory = __import__("core.memory.store", fromlist=["MemoryStore"]).MemoryStore(
            base_dir=str(tmp_path / "memory")
        )
        brain = Brain(bus=object(), skill_loader=loader, memory=memory)

        speaker = Device(
            device_id="speaker_01",
            name="Xiaomi Smart Speaker",
            adapter="miot",
            type="speaker",
            capabilities=[Capability(name="play_random_audio"), Capability(name="stop_audio")],
        )

        class FakeDiscovery:
            def __init__(self, target):
                self.target = target
                self.executed = []
                self.refreshed = 0

            def get_all_devices(self):
                return [self.target]

            def get_devices_by_type(self, device_type):
                return [self.target] if device_type == "speaker" else []

            async def execute_command(self, device_id, action, params):
                self.executed.append((device_id, action, params))
                return type("Result", (), {"message": "", "success": True})()

            async def refresh_device_states(self, device_ids=None):
                self.refreshed += 1
                return {"refreshed": 1, "failed": 0}

            def get_device(self, device_id):
                return self.target if device_id == self.target.device_id else None

        class FakeSettings:
            def get(self, key, default=None):
                if key == "llm_api_key":
                    return "sk-test"
                return default

        discovery = FakeDiscovery(speaker)
        brain.set_environment_provider(discovery.get_all_devices)
        brain._invoke_llm_text = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value='{"reply":"我先确认环境再播放。","should_execute":true,"task_plan_items":[{"kind":"refresh_environment","reason":"need latest state","priority":5},{"kind":"execute_skill","skill_name":"speaker","goal":"play random music on the speaker","reason":"user asked to play music","priority":10}]}'
        )

        result = await brain.handle_chat_message(
            "随机放一首歌",
            {"discovery": discovery, "settings": FakeSettings(), "brain": brain},
        )

        assert result["executed"] is True
        assert result["execution_results"][0]["actions"][0]["action"] == "play_random_audio"
        assert result["task_results"][0]["kind"] == "refresh_environment"
        assert discovery.refreshed >= 2
