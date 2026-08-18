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
    jwt_expire_minutes: int = 1440

    # Frontend URL (for redirects)
    local_frontend_url: str = "http://localhost:3000"
    prod_frontend_url: str = ""

    # Azure Blob Storage / Azurite
    azure_storage_connection_string: str = ""
    azure_storage_account_name: str = "devstoreaccount1"
    azure_storage_account_key: str = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
    azure_storage_container: str = "gitonboard-repos"
    azure_storage_endpoint: str = "http://azurite:10000/devstoreaccount1"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def database_url(self) -> str:
        return self.local_database_url if self.deployment_type == "LOCAL" else self.prod_database_url

    @property
    def frontend_url(self) -> str:
        return self.local_frontend_url if self.deployment_type == "LOCAL" else self.prod_frontend_url

settings = Settings()
