# One polyglot image used only for verification's build/test execution
# (DynamicVerifier -> DockerVerificationRunner). NOT used for the agent's
# code-writing step, and NEVER given access to the Docker socket itself.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NPM_CONFIG_LOGLEVEL=warn

# Node.js (LTS) + git + minimal build tooling for native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && pip install --no-cache-dir pytest \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash verifier
USER verifier
WORKDIR /workspace

CMD ["/bin/bash"]
