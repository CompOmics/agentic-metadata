"""
Static validation tests for Docker configuration files.

These tests run without Docker — they parse and validate the config files
directly to catch common issues before a build is attempted.
"""

import re
from pathlib import Path

import pytest
import yaml

DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"
COMPOSE_FILE = DOCKER_DIR / "docker-compose.yml"
DOCKERFILE = DOCKER_DIR / "Dockerfile"
ENTRYPOINT = DOCKER_DIR / "ollama-entrypoint.sh"
COMPOSE_GPU = DOCKER_DIR / "docker-compose.gpu.yml"
LAUNCH_SH = DOCKER_DIR / "launch.sh"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text()


@pytest.fixture(scope="module")
def entrypoint_text() -> str:
    return ENTRYPOINT.read_text()


@pytest.fixture(scope="module")
def launch_text() -> str:
    return LAUNCH_SH.read_text()


# ── Dockerfile ────────────────────────────────────────────────────────────────

class TestDockerfile:
    def test_noninteractive_env(self, dockerfile_text):
        """DEBIAN_FRONTEND=noninteractive must be set to prevent apt timezone prompts."""
        assert "DEBIAN_FRONTEND=noninteractive" in dockerfile_text

    def test_tz_set(self, dockerfile_text):
        """TZ must be set to prevent tzdata from blocking the build."""
        assert "TZ=UTC" in dockerfile_text

    def test_python312(self, dockerfile_text):
        assert "python3.12" in dockerfile_text

    def test_entrypoint_uses_run_docetl(self, dockerfile_text):
        assert "run_docetl.py" in dockerfile_text

    def test_pythonpath_set(self, dockerfile_text):
        assert "PYTHONPATH=/app" in dockerfile_text


# ── docker-compose.yml ────────────────────────────────────────────────────────

class TestDockerCompose:
    def test_llm_service_exists(self, compose):
        assert "llm" in compose["services"]

    def test_docetl_service_exists(self, compose):
        assert "docetl" in compose["services"]

    def test_container_name_is_hamlet(self, compose):
        """LLM container must be named 'hamlet', not the old 'pride-llm'."""
        name = compose["services"]["llm"].get("container_name", "")
        assert name == "hamlet", f"Expected 'hamlet', got '{name}'"

    def test_no_pride_llm_name(self, compose):
        name = compose["services"]["llm"].get("container_name", "")
        assert "pride" not in name.lower()

    def test_default_model_is_gemma4(self, compose):
        env = compose["services"]["llm"].get("environment", [])
        model_vars = [e for e in env if "MODEL_NAME" in e]
        assert model_vars, "MODEL_NAME env var not found"
        assert "gemma4" in model_vars[0]

    def test_docetl_depends_on_llm(self, compose):
        deps = compose["services"]["docetl"].get("depends_on", {})
        assert "llm" in deps

    def test_healthcheck_present(self, compose):
        hc = compose["services"]["llm"].get("healthcheck")
        assert hc is not None
        assert hc.get("retries", 0) >= 10

    def test_healthcheck_references_gemma4(self, compose):
        hc = compose["services"]["llm"]["healthcheck"]
        test_cmd = " ".join(hc["test"])
        assert "gemma4" in test_cmd

    def test_named_volumes_defined(self, compose):
        volumes = compose.get("volumes", {})
        for vol in ("ollama_models", "hf_cache", "docetl_cache"):
            assert vol in volumes, f"Named volume '{vol}' missing"


# ── ollama-entrypoint.sh ──────────────────────────────────────────────────────

class TestEntrypoint:
    def test_default_model_is_gemma4(self, entrypoint_text):
        """Default fallback model in entrypoint must match compose default."""
        assert "gemma4" in entrypoint_text

    def test_no_qwen_default(self, entrypoint_text):
        """Old Qwen default must not remain as the fallback."""
        # Allow qwen references in comments but not as the default value
        default_line = next(
            (l for l in entrypoint_text.splitlines() if "MODEL_NAME:-" in l), ""
        )
        assert "qwen" not in default_line.lower()

    def test_ollama_serve_called(self, entrypoint_text):
        assert "ollama serve" in entrypoint_text

    def test_model_pull_called(self, entrypoint_text):
        assert "ollama pull" in entrypoint_text


# ── launch.sh ────────────────────────────────────────────────────────────────

class TestLaunchSh:
    def test_gpu_model_is_gemma4_31b(self, launch_text):
        gpu_line = next(
            (l for l in launch_text.splitlines() if "GPU_MODEL=" in l), ""
        )
        assert "gemma4:31b" in gpu_line

    def test_cpu_model_is_gemma4_12b(self, launch_text):
        cpu_line = next(
            (l for l in launch_text.splitlines() if "CPU_MODEL=" in l), ""
        )
        assert "gemma4:12b" in cpu_line

    def test_no_qwen_models(self, launch_text):
        for line in launch_text.splitlines():
            if "GPU_MODEL=" in line or "CPU_MODEL=" in line:
                assert "qwen" not in line.lower(), f"Qwen still referenced: {line}"

    def test_nvidia_smi_detection(self, launch_text):
        assert "nvidia-smi" in launch_text

    def test_cpu_only_flag(self, launch_text):
        assert "--cpu-only" in launch_text

    def test_gpu_flag(self, launch_text):
        assert "--gpu" in launch_text
