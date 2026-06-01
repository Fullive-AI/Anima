from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "ANIMA_", "env_file": ".env", "extra": "ignore"}

    # LLM
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: str | None = None
    llm_disable_thinking: bool = False

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # Xiaomi Cloud (optional, for token acquisition)
    xiaomi_cloud_user: str = ""
    xiaomi_cloud_pass: str = ""

    # Paths
    data_dir: str = "data"
    skills_dir: str = "skills"
    audio_library_dir: str = ""


settings = Settings()
