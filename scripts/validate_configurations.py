"""
FraudShield 3.0 Configuration, Container Spec & Health Probe Validator.
Validates:
1. Dockerfile.v3 security hardening, multi-stage structure, non-root user, OpenMP runtime, health probes.
2. docker-compose.v3.yml YAML structure, service definitions, healthcheck conditions, resource limits.
3. config/redis.conf AOF persistence, memory limits, eviction policy, snapshotting.
4. Environment variables templates & .env.pilot completeness.
5. In-memory / HTTP execution of /health/live and /health/ready probes.
"""

import sys
import re
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def validate_dockerfile(dockerfile_path: Path) -> dict:
    content = dockerfile_path.read_text(encoding="utf-8")
    checks = {
        "multi_stage": "AS builder" in content and "AS runtime" in content,
        "base_image_python312": "python:3.12-slim-bookworm" in content,
        "non_root_user": "fraudshield" in content and "10001" in content and "USER fraudshield" in content,
        "openmp_runtime": "libgomp1" in content,
        "healthcheck_defined": "HEALTHCHECK" in content and "/health/ready" in content,
        "workers_configured": "--workers" in content and "4" in content,
    }
    all_passed = all(checks.values())
    return {"passed": all_passed, "checks": checks}


def validate_compose(compose_path: Path) -> dict:
    content = compose_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    services = data.get("services", {})
    api = services.get("fraudshield-api", {})
    redis_svc = services.get("redis-store", {})

    checks = {
        "has_api_service": "fraudshield-api" in services,
        "has_redis_service": "redis-store" in services,
        "api_depends_on_redis_healthy": (
            api.get("depends_on", {}).get("redis-store", {}).get("condition") == "service_healthy"
        ),
        "api_healthcheck": bool(api.get("healthcheck", {}).get("test")),
        "redis_healthcheck": bool(redis_svc.get("healthcheck", {}).get("test")),
        "resource_limits_defined": bool(api.get("deploy", {}).get("resources", {}).get("limits")),
        "redis_config_mounted": any("redis.conf" in v for v in redis_svc.get("volumes", [])),
    }
    all_passed = all(checks.values())
    return {"passed": all_passed, "checks": checks}


def validate_redis_conf(redis_conf_path: Path) -> dict:
    content = redis_conf_path.read_text(encoding="utf-8")
    checks = {
        "appendonly_yes": bool(re.search(r"^\s*appendonly\s+yes", content, re.MULTILINE)),
        "appendfsync_everysec": bool(re.search(r"^\s*appendfsync\s+everysec", content, re.MULTILINE)),
        "maxmemory_set": bool(re.search(r"^\s*maxmemory\s+\d+", content, re.MULTILINE)),
        "maxmemory_policy_volatile_lru": bool(re.search(r"^\s*maxmemory-policy\s+volatile-lru", content, re.MULTILINE)),
        "rdb_snapshotting_configured": bool(re.search(r"^\s*save\s+\d+\s+\d+", content, re.MULTILINE)),
    }
    all_passed = all(checks.values())
    return {"passed": all_passed, "checks": checks}


def validate_env_templates(prod_template: Path, pilot_env: Path) -> dict:
    prod_text = prod_template.read_text(encoding="utf-8")
    pilot_text = pilot_env.read_text(encoding="utf-8")

    required_vars = [
        "FRAUDSHIELD_TOKEN_SALT",
        "FRAUDSHIELD_API_KEY_SALT",
        "FRAUDSHIELD_ADMIN_API_KEY",
        "FRAUDSHIELD_SERVICE_API_KEY",
        "FRAUDSHIELD_ANALYST_API_KEY",
        "FRAUDSHIELD_REDIS_URL",
        "RATE_LIMIT_SERVICE_PER_MIN",
        "DEGRADED_FAILSAFE_ENABLED",
    ]

    checks = {
        "prod_template_has_all_vars": all(var in prod_text for var in required_vars),
        "pilot_env_has_all_vars": all(var in pilot_text for var in required_vars),
        "pilot_salts_injected": "REPLACE_WITH" not in pilot_text,
    }
    all_passed = all(checks.values())
    return {"passed": all_passed, "checks": checks}


def test_health_probes():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    live_resp = client.get("/health/live")
    ready_resp = client.get("/health/ready")

    checks = {
        "live_status_200": live_resp.status_code == 200,
        "live_payload_alive": live_resp.json().get("status") == "ALIVE",
        "ready_status_200": ready_resp.status_code == 200,
        "ready_model_loaded": ready_resp.json().get("model_loaded") is True,
        "ready_auth_ready": ready_resp.json().get("auth_ready") is True,
    }
    all_passed = all(checks.values())
    return {"passed": all_passed, "checks": checks, "live_data": live_resp.json(), "ready_data": ready_resp.json()}


def main():
    print("=" * 80)
    print("FRAUDSHIELD 3.0 — CONFIGURATION & HEALTH PROBE VALIDATION")
    print("=" * 80)

    df_res = validate_dockerfile(PROJECT_ROOT / "Dockerfile.v3")
    print(f"\n[1] Dockerfile.v3 Validation: {'PASS' if df_res['passed'] else 'FAIL'}")
    for k, v in df_res["checks"].items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")

    dc_res = validate_compose(PROJECT_ROOT / "docker-compose.v3.yml")
    print(f"\n[2] docker-compose.v3.yml Validation: {'PASS' if dc_res['passed'] else 'FAIL'}")
    for k, v in dc_res["checks"].items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")

    rc_res = validate_redis_conf(PROJECT_ROOT / "config" / "redis.conf")
    print(f"\n[3] config/redis.conf Validation: {'PASS' if rc_res['passed'] else 'FAIL'}")
    for k, v in rc_res["checks"].items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")

    env_res = validate_env_templates(PROJECT_ROOT / ".env.production.template", PROJECT_ROOT / ".env.pilot")
    print(f"\n[4] Environment Variables Validation: {'PASS' if env_res['passed'] else 'FAIL'}")
    for k, v in env_res["checks"].items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")

    hp_res = test_health_probes()
    print(f"\n[5] Health Probes Live Testing: {'PASS' if hp_res['passed'] else 'FAIL'}")
    for k, v in hp_res["checks"].items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")
    print(f"    Readiness probe response payload: {hp_res['ready_data']}")

    overall = all([df_res["passed"], dc_res["passed"], rc_res["passed"], env_res["passed"], hp_res["passed"]])
    print("\n" + "=" * 80)
    print(f"OVERALL CONFIGURATION VALIDATION: {'ALL PASSED' if overall else 'FAILED'}")
    print("=" * 80)
    if not overall:
        sys.exit(1)


if __name__ == "__main__":
    main()
