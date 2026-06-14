"""Toolset exposure tests for Feishu GitHub PR approval cards."""

from toolsets import resolve_toolset


def test_github_pr_approval_card_is_exposed_to_feishu_toolset():
    assert "github_pr_approval_card" in resolve_toolset("hermes-feishu")


def test_github_pr_approval_card_is_exposed_to_messaging_toolset():
    assert "github_pr_approval_card" in resolve_toolset("messaging")
