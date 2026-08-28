"""Tests for task-workbench model metadata loaded from config.yaml."""


def test_progress_model_config_uses_trimmed_raw_config_values(monkeypatch):
    import gateway.run as gateway_run
    from gateway.run import GatewayRunner

    monkeypatch.setattr(
        gateway_run,
        "_load_gateway_runtime_config",
        lambda: {"agent": {"reasoning_effort": "  custom-effort  ", "service_tier": " fast "}},
    )

    assert GatewayRunner._load_progress_model_config_display() == ("custom-effort", "fast")


def test_progress_model_config_omits_missing_values(monkeypatch):
    import gateway.run as gateway_run
    from gateway.run import GatewayRunner

    monkeypatch.setattr(gateway_run, "_load_gateway_runtime_config", lambda: {"agent": {}})

    assert GatewayRunner._load_progress_model_config_display() == (None, None)
