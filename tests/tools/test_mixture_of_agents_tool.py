"""Sachima MoA preservation acceptance against the upstream turn facade.

The downstream implementation was a model tool with a hard-coded OpenRouter
catalog. Upstream's `/moa` facade is the lower-footprint equivalent: it reads
named preset slots from config, fans reference calls out in parallel, then
lets the configured aggregator remain the acting model in the normal tool
loop. These tests preserve the business behavior without restoring a model
tool on every request.
"""

from __future__ import annotations

from types import SimpleNamespace


def _completion(content: str, model: str):
    message = SimpleNamespace(content=content, tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model=model)


def test_configured_references_fan_out_before_configured_aggregator(
    tmp_path, monkeypatch
) -> None:
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        """
moa:
  default_preset: sachima-acceptance
  presets:
    sachima-acceptance:
      enabled: true
      reference_models:
        - provider: openrouter
          model: sachima/reference-one
        - provider: openrouter
          model: sachima/reference-two
      aggregator:
        provider: openrouter
        model: sachima/aggregator
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))

    calls: list[dict] = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        model = kwargs["model"]
        if kwargs.get("task") == "moa_reference":
            return _completion(f"advice from {model}", model)
        return _completion("synthesized answer", model)

    monkeypatch.setattr("agent.moa_loop.call_llm", fake_call_llm)
    monkeypatch.setattr(
        "agent.moa_loop._slot_runtime",
        lambda slot: {"provider": slot["provider"], "model": slot["model"]},
    )
    monkeypatch.setattr(
        "agent.moa_loop._trim_messages_for_reference",
        lambda messages, *_args, **_kwargs: messages,
    )

    from agent.moa_loop import MoAChatCompletions

    result = MoAChatCompletions("sachima-acceptance").create(
        model="sachima-acceptance",
        messages=[{"role": "user", "content": "Solve the business problem"}],
    )

    reference_calls = [call for call in calls if call.get("task") == "moa_reference"]
    aggregator_calls = [call for call in calls if call.get("task") == "moa_aggregator"]
    assert {call["model"] for call in reference_calls} == {
        "sachima/reference-one",
        "sachima/reference-two",
    }
    assert len(aggregator_calls) == 1
    assert aggregator_calls[0]["model"] == "sachima/aggregator"
    aggregator_input = str(aggregator_calls[0]["messages"][-1]["content"])
    assert "advice from sachima/reference-one" in aggregator_input
    assert "advice from sachima/reference-two" in aggregator_input
    assert result.choices[0].message.content == "synthesized answer"


def test_moa_models_resolve_from_named_preset_not_module_catalog() -> None:
    from hermes_cli.moa_config import resolve_moa_preset

    raw = {
        "presets": {
            "custom": {
                "reference_models": [
                    {"provider": "provider-a", "model": "model-a"},
                    {"provider": "provider-b", "model": "model-b"},
                ],
                "aggregator": {"provider": "provider-c", "model": "model-c"},
            }
        }
    }

    preset = resolve_moa_preset(raw, "custom")

    assert [slot["model"] for slot in preset["reference_models"]] == [
        "model-a",
        "model-b",
    ]
    assert preset["aggregator"] == {
        "provider": "provider-c",
        "model": "model-c",
    }
