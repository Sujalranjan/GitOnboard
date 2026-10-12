from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Repository Intelligence Platform"
    environment: str = "development"
    deployment_type: str = "LOCAL"

    # Storage & Sandbox Config
    storage_path: str = "data"
    worktrees_dir: str = "data/worktrees"
    workspace_dir: str = "."

    # Verification Sandbox Config
    #
    # Docker-outside-of-Docker (DooD) path translation for DockerVerificationRunner
    # (backend/verification/docker_runner.py). Three distinct roots are in play
    # whenever the backend itself runs containerized and spawns sibling
    # verification containers via the host Docker socket — conflating any two
    # of them is exactly what makes bind mounts silently fail to resolve:
    #   1. HOST_DATA_DIR              — where ./data lives on the HOST filesystem
    #                                   (what the HOST Docker daemon can mount).
    #   2. BACKEND_CONTAINER_DATA_DIR — where that same ./data is mounted INSIDE
    #                                   the backend container (docker-compose.yml
    #                                   mounts it at /app/data).
    #   3. VERIFICATION_CONTAINER_WORKDIR — where the worktree is bind-mounted
    #                                   INSIDE the verification container.
    verification_use_docker: bool = True
    verification_docker_image: str = "gitonboard-verification:latest"
    # (1) Host-side path of ./data. Empty when the backend runs directly on
    # the host (dev outside Compose) — container paths already ARE host paths,
    # so no translation is needed at all.
    host_data_dir: str = ""
    # (2) Path where ./data is mounted inside the *backend* container. Empty
    # means "infer from storage_path" (correct when the backend runs natively
    # on the host, where storage_path IS already the real filesystem root).
    # Compose sets this explicitly to /app/data rather than relying on
    # inference, since storage_path ("data") resolved against the container's
    # cwd happens to also land on /app/data today — but that's an accident of
    # WORKDIR, not a contract, and DooD path translation should not depend on it.
    backend_container_data_dir: str = ""
    # (3) Mount target inside the ephemeral *verification* container.
    verification_container_workdir: str = "/workspace"

    # Database
    local_database_url: str = "postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence"
    prod_database_url: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # JWT Config
    jwt_secret: str = "change_me_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days instead of 1 day

    # Frontend URL (for redirects)
    local_frontend_url: str = "http://localhost:3000"
    prod_frontend_url: str = ""

    # Azure Blob Storage / Azurite (LOCAL)
    azure_storage_connection_string: str = ""
    azure_storage_account_name: str = "devstoreaccount1"
    azure_storage_account_key: str = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
    azure_storage_container: str = "gitonboard-repos"
    azure_storage_endpoint: str = "http://azurite:10000/devstoreaccount1"

    # Azure Blob Storage (PROD)
    prod_azure_storage_connection_string: str = ""
    prod_azure_storage_account_name: str = ""
    prod_azure_storage_account_key: str = ""
    prod_azure_storage_endpoint: str = ""
    prod_azure_storage_container: str = "gitonboard-repos"

    # Terminal Model Routing Configuration
    # Intent + chat use the lightweight instruct model (fast, low memory)
    model_intent_router: str = "qwen3:4b-instruct"
    model_terminal_chat: str = "qwen3:4b-instruct"
    model_terminal_clarify: str = "qwen3:4b-instruct"
    # Coding tasks: currently using qwen3:4b-instruct as primary (fast & fits in memory).
    # To switch back to the coder model, set these to "qwen2.5-coder:7b"
    # (or override per-model via .env: MODEL_TERMINAL_EXPLAIN=qwen2.5-coder:7b etc.)
    model_terminal_explore: str = "qwen3:4b-instruct"
    model_terminal_explain: str = "qwen3:4b-instruct"
    model_terminal_plan: str = "qwen3:4b-instruct"
    model_terminal_implement: str = "qwen3:4b-instruct"

    # LOCAL mode models (Ollama/Qwen)
    model_local_default: str = "qwen3:4b-instruct"
    model_local_fast: str = "qwen3:4b-instruct"
    model_local_quality: str = "qwen2.5-coder:7b"
    model_local_max_tokens: int = 8192

    # PROD mode models (Cloud providers: Gemini, OpenRouter, Groq)
    # Use actual model names (e.g., "gemini-3.8-flash", "nvidia/nemotron-3-ultra-550b-a55b:free", "openai/gpt-oss-120b")
    model_prod_default: str = "gemini-3.8-flash"
    gemini_model: str = "gemini-3.8-flash"
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    groq_model: str = "openai/gpt-oss-120b"
    model_prod_max_tokens: int = 65536

    # Provider Context & Token Budget Settings (Configurable Application Defaults)
    # Groq (openai/gpt-oss-120b)
    groq_context_window: int = 65536
    groq_input_tpm: int = 8000
    groq_single_request_limit: int = 8000
    groq_safety_margin_tokens: int = 600
    groq_control_reservation_tokens: int = 150
    groq_output_reservation_tokens: int = 1024

    # Gemini (gemini-3.8-flash)
    gemini_context_window: int = 1048576
    gemini_input_tpm: int = 250000
    gemini_single_request_limit: int = 65536  # Application ceiling, decoupled from 250K TPM
    gemini_safety_margin_tokens: int = 2000
    gemini_control_reservation_tokens: int = 200
    gemini_output_reservation_tokens: int = 4096

    # OpenRouter (nvidia/nemotron-3-ultra-550b-a55b:free or configured model)
    openrouter_context_window: int = 1000000
    openrouter_input_tpm: int = 0  # 0 indicates not tracked/unconstrained
    openrouter_single_request_limit: int = 0  # 0 indicates not clamped by a fixed provider ceiling
    openrouter_safety_margin_tokens: int = 1500
    openrouter_control_reservation_tokens: int = 200
    openrouter_output_reservation_tokens: int = 2048

    # Investigation Agent Configuration (LOCAL vs PROD)
    # Output tokens
    investigation_synthesis_max_tokens_local: int = 4096
    investigation_synthesis_max_tokens_prod: int = 16384
    investigation_turn_max_tokens_local: int = 2048
    investigation_turn_max_tokens_prod: int = 8192

    # Concurrency and subtask counts
    investigation_concurrency_local: int = 1
    investigation_concurrency_prod: int = 5
    investigation_max_turns_local: int = 10
    investigation_max_turns_prod: int = 35
    investigation_max_total_tasks_local: int = 6
    investigation_max_total_tasks_prod: int = 20

    # Wall-clock timeouts and observations
    investigation_subtask_timeout_local: float = 600.0   # 10 min
    investigation_subtask_timeout_prod: float = 1200.0   # 20 min
    investigation_max_observation_chars_local: int = 24000
    investigation_max_observation_chars_prod: int = 120000

    # Tool limits
    investigation_read_file_max_lines_local: int = 600
    investigation_read_file_max_lines_prod: int = 1000
    investigation_search_limit_local: int = 10
    investigation_search_limit_prod: int = 50

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def database_url(self) -> str:
        if self.deployment_type == "TEST":
            return "sqlite+pysqlite:///:memory:"
        if self.deployment_type == "PROD" and self.prod_database_url.strip():
            return self.prod_database_url
        return self.local_database_url

    @property
    def frontend_url(self) -> str:
        if self.deployment_type == "PROD" and self.prod_frontend_url.strip():
            return self.prod_frontend_url
        return self.local_frontend_url

    @property
    def llm_max_tokens(self) -> int:
        """Return max tokens based on deployment mode."""
        if self.deployment_type == "PROD":
            return self.model_prod_max_tokens
        return self.model_local_max_tokens

    @property
    def effective_azure_storage_connection_string(self) -> str:
        if self.deployment_type == "PROD" and self.prod_azure_storage_connection_string.strip():
            return self.prod_azure_storage_connection_string.strip()
        return self.azure_storage_connection_string.strip()

    @property
    def effective_azure_storage_account_name(self) -> str:
        if self.deployment_type == "PROD" and self.prod_azure_storage_account_name.strip():
            return self.prod_azure_storage_account_name.strip()
        return self.azure_storage_account_name.strip()

    @property
    def effective_azure_storage_account_key(self) -> str:
        if self.deployment_type == "PROD" and self.prod_azure_storage_account_key.strip():
            return self.prod_azure_storage_account_key.strip()
        return self.azure_storage_account_key.strip()

    @property
    def effective_azure_storage_endpoint(self) -> str:
        if self.deployment_type == "PROD" and self.prod_azure_storage_endpoint.strip():
            return self.prod_azure_storage_endpoint.strip()
        return self.azure_storage_endpoint.strip()

    @property
    def effective_azure_storage_container(self) -> str:
        if self.deployment_type == "PROD" and self.prod_azure_storage_container.strip():
            return self.prod_azure_storage_container.strip()
        return self.azure_storage_container.strip()

    @property
    def is_prod(self) -> bool:
        return str(self.deployment_type).strip().upper() == "PROD"

    @property
    def investigation_synthesis_max_tokens(self) -> int:
        return self.investigation_synthesis_max_tokens_prod if self.is_prod else self.investigation_synthesis_max_tokens_local

    @property
    def investigation_turn_max_tokens(self) -> int:
        return self.investigation_turn_max_tokens_prod if self.is_prod else self.investigation_turn_max_tokens_local

    @property
    def investigation_concurrency(self) -> int:
        return self.investigation_concurrency_prod if self.is_prod else self.investigation_concurrency_local

    @property
    def investigation_max_turns(self) -> int:
        return self.investigation_max_turns_prod if self.is_prod else self.investigation_max_turns_local

    @property
    def investigation_max_total_tasks(self) -> int:
        return self.investigation_max_total_tasks_prod if self.is_prod else self.investigation_max_total_tasks_local

    @property
    def investigation_subtask_timeout(self) -> float:
        return self.investigation_subtask_timeout_prod if self.is_prod else self.investigation_subtask_timeout_local

    @property
    def investigation_max_observation_chars(self) -> int:
        return self.investigation_max_observation_chars_prod if self.is_prod else self.investigation_max_observation_chars_local

    @property
    def investigation_read_file_max_lines(self) -> int:
        return self.investigation_read_file_max_lines_prod if self.is_prod else self.investigation_read_file_max_lines_local

    @property
    def investigation_search_limit(self) -> int:
        return self.investigation_search_limit_prod if self.is_prod else self.investigation_search_limit_local

settings = Settings()
