import { describe, expect, it } from "vitest";

import { displayTodoExecutor } from "./todo-executor";

describe("displayTodoExecutor", () => {
  it("accepts compact lowercase tokens", () => {
    expect(displayTodoExecutor("claude")).toBe("claude");
    expect(displayTodoExecutor("codex")).toBe("codex");
    expect(displayTodoExecutor("other")).toBe("other");
    expect(displayTodoExecutor("gemini-cli")).toBe("gemini-cli");
    expect(displayTodoExecutor("qwen_coder.v2")).toBe("qwen_coder.v2");
  });

  it("trims and lowercases", () => {
    expect(displayTodoExecutor("  Claude  ")).toBe("claude");
    expect(displayTodoExecutor("CODEX")).toBe("codex");
  });

  it("aliases hermes-agent to the short display form", () => {
    expect(displayTodoExecutor("hermes-agent")).toBe("hermes");
    expect(displayTodoExecutor("  Hermes-Agent  ")).toBe("hermes");
    expect(displayTodoExecutor("hermes")).toBe("hermes");
  });

  it("drops invalid or hostile values entirely", () => {
    expect(displayTodoExecutor(null)).toBeNull();
    expect(displayTodoExecutor(undefined)).toBeNull();
    expect(displayTodoExecutor(123)).toBeNull();
    expect(displayTodoExecutor("")).toBeNull();
    expect(displayTodoExecutor("two words")).toBeNull();
    expect(displayTodoExecutor("a".repeat(33))).toBeNull();
    expect(displayTodoExecutor("-leading-dash")).toBeNull();
    expect(displayTodoExecutor("https://evil.example/agent")).toBeNull();
    expect(displayTodoExecutor("agent:role")).toBeNull();
    expect(displayTodoExecutor("user@host")).toBeNull();
    expect(displayTodoExecutor("[claude](https://evil.example)")).toBeNull();
    expect(displayTodoExecutor("<at id=ou_x>bot</at>")).toBeNull();
    expect(displayTodoExecutor("代理")).toBeNull();
  });

  it("drops credential-shaped values", () => {
    expect(displayTodoExecutor("sk-" + "a".repeat(24))).toBeNull();
    expect(displayTodoExecutor("ghp_" + "b".repeat(24))).toBeNull();
    expect(displayTodoExecutor("xoxb-slack-token")).toBeNull();
    expect(displayTodoExecutor("hf_" + "d".repeat(20))).toBeNull();
    expect(displayTodoExecutor("pat_token")).toBeNull();
  });
});
