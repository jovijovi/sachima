---
sidebar_position: 16
title: "Google Gemini"
description: "Use Hermes Agent with Google Gemini through the native AI Studio API or Google's official Gemini CLI account login"
---

# Google Gemini

Hermes Agent supports two distinct Google Gemini paths:

- **Google AI Studio / Gemini API** (`provider: gemini`) uses an API key and Hermes' native `generateContent` adapter.
- **Official Gemini CLI** (`provider: google-gemini-cli`) uses the Google account already signed in to Google's `gemini` command and communicates only through its documented ACP stdio mode.

The second path does not copy or replay OAuth tokens and does not call the private Cloud Code Assist service directly. Google explicitly requires third-party tools to use supported integration surfaces rather than piggybacking Gemini CLI OAuth credentials; see the official [Gemini CLI terms and privacy guidance](https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/tos-privacy.md) and [ACP mode documentation](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/acp-mode.md).

## Prerequisites

Choose one credential path:

- **API key:** create a Google AI Studio key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). A billing-enabled Google Cloud project is recommended for long-running agent sessions.
- **Google account:** install the official [Gemini CLI](https://github.com/google-gemini/gemini-cli), run `gemini` interactively, and choose **Sign in with Google**. Hermes never reads its credential files.

Hermes itself needs no extra Python package for either path.

:::tip API key path
Set `GOOGLE_API_KEY` or `GEMINI_API_KEY`. Hermes checks both names for the `gemini` provider.
:::

## Quick Start: API Key

```bash
# Add your Gemini API key
echo "GOOGLE_API_KEY=..." >> ~/.hermes/.env

# Select Gemini as your provider
hermes model
# → Choose "More providers..." → "Google AI Studio"
# → Hermes checks your key tier and shows Gemini models
# → Select a model

# Start chatting
hermes chat
```

If you prefer direct config editing, use the native Gemini API base URL:

```yaml
model:
  default: gemini-3.7-flash
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta
```

## Quick Start: Official Gemini CLI Account

Install and authenticate Google's CLI first:

```bash
npm install -g @google/gemini-cli
gemini
# Choose "Sign in with Google", complete Google's flow, then exit.

hermes model
# → Choose "Google" → "Google Gemini CLI"
hermes chat
```

The resulting Hermes configuration uses a local transport marker, not a web API endpoint:

```yaml
model:
  default: gemini-cli
  provider: google-gemini-cli
  base_url: acp://gemini
  api_mode: chat_completions
```

`gemini-cli` means “use the official CLI's current default model.” You may instead configure a specific Gemini model ID; Hermes passes it to the official process with `--model`. The aliases `gemini-cli` and `gemini-oauth` resolve to `google-gemini-cli` for older configs.

:::important Supported OAuth boundary
Do not paste a Gemini CLI OAuth token into Hermes. Authentication, refresh, account eligibility, and quota enforcement remain inside Google's CLI. Hermes starts `gemini --acp`, sends ACP JSON-RPC over stdio, and uses the login state the CLI already owns.
:::

## Configuration

After running `hermes model`, your `~/.hermes/config.yaml` will contain:

```yaml
model:
  default: gemini-3.7-flash
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta
```

And in `~/.hermes/.env`:

```bash
GOOGLE_API_KEY=...
```

### Native Gemini API

The recommended endpoint is:

```text
https://generativelanguage.googleapis.com/v1beta
```

Hermes detects this endpoint and creates its native Gemini adapter. Internally, Hermes still keeps the agent loop in OpenAI-shaped messages, then translates each request to Gemini's native schema:

- `messages[]` → Gemini `contents[]`
- system prompts → Gemini `systemInstruction`
- tool schemas → Gemini `functionDeclarations`
- tool results → Gemini `functionResponse` parts
- streaming responses → OpenAI-shaped stream chunks for the Hermes loop

:::note Gemini 3 thought signatures
For Gemini 3 tool use, Hermes preserves the `thoughtSignature` values attached to function-call parts and replays them on the next tool turn. That covers the validation-critical path for multi-step agent workflows.

Gemini 3 may also attach thought signatures to other response parts. Hermes' native adapter is optimized for agent tool loops today, so it does not yet replay every non-tool-call signature with full part-level fidelity.
:::

### Prefer the Native Endpoint

Google also exposes an OpenAI-compatible endpoint:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

For Hermes agent sessions, prefer the native Gemini endpoint above. Hermes includes a native Gemini adapter so it can map multi-turn tool use, tool-call results, streaming, multimodal inputs, and Gemini response metadata directly onto Gemini's `generateContent` API. The OpenAI-compatible endpoint is still useful when you specifically need OpenAI API compatibility.

If you previously set `GEMINI_BASE_URL` to the `/openai` URL, remove it or change it:

```bash
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

## Available Models

The `hermes model` picker shows Gemini models maintained in Hermes' provider registry. Common choices include:

| Model | ID | Notes |
|-------|----|-------|
| Gemini 3.7 Flash | `gemini-3.7-flash` | Recommended default balance of speed, capability, and multimodal understanding |
| Gemini 3.1 Pro Preview | `gemini-3.1-pro-preview` | Most capable reasoning, math, and coding model |
| Gemini 3.5 Flash Lite | `gemini-3.5-flash-lite` | Fastest and lowest-cost option for lightweight tasks |
| Gemini 2.5 Flash | `gemini-2.5-flash` | Previous generation fast model with thinking capabilities |
| Gemini 2.5 Pro | `gemini-2.5-pro` | Previous generation complex reasoning model |

Model availability changes over time. If a model disappears or is not enabled for your key, run `hermes model` again and pick one from the current list.

:::info Model IDs
Use Gemini's native model IDs such as `gemini-3.7-flash`, not OpenRouter-style IDs like `google/gemini-3.7-flash`, when `provider: gemini`.
:::

### Latest Aliases

Google publishes moving aliases for the Pro and Flash Gemini families. `gemini-pro-latest` and `gemini-flash-latest` are useful when you want Google to advance the model automatically without changing your Hermes config. Note that your usage charges may be affected if newer models introduce different rates.

| Alias | Currently tracks | Notes |
|-------|------------------|-------|
| `gemini-pro-latest` | Latest Gemini Pro model | Best when you want Google's current Pro default |
| `gemini-flash-latest` | Latest Gemini Flash model | Best when you want Google's current Flash default |

```yaml
model:
  default: gemini-pro-latest
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta
```

If you need strict reproducibility, prefer explicit model IDs such as `gemini-3.1-pro-preview` or `gemini-3.7-flash`.

### Gemma via the Gemini API

Google also exposes Gemma models through the Gemini API. Hermes recognizes these as Google models, but hides very low-throughput Gemma entries from the default model picker so new users do not accidentally select an evaluation-tier model for a long-running agent session.

Useful evaluation IDs include:

| Model | ID | Notes |
|-------|----|-------|
| Gemma 4 31B IT | `gemma-4-31b-it` | Larger Gemma model; useful for compatibility and quality evaluation |
| Gemma 4 26B A4B IT | `gemma-4-26b-a4b-it` | Smaller active-parameter variant when available |

These models are best treated as evaluation options on Gemini API keys. Google's Gemma API pricing is free-tier-only and the usage caps are low compared with production Gemini models, so sustained Hermes agent use should normally move to a paid Gemini model, a self-hosted deployment, or another provider with appropriate quota.

To use a Gemma model that is hidden from the picker, set it directly:

```yaml
model:
  default: gemma-4-31b-it
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta
```

## Switching Models Mid-Session

Use the `/model` command during a conversation:

```text
/model gemini-3.7-flash
/model gemini-flash-latest
/model gemini-3.1-pro-preview
/model gemini-pro-latest
/model gemma-4-31b-it
/model gemini-3.1-flash-lite-preview
```

If you have not configured Gemini yet, exit the session and run `hermes model` first. `/model` switches among already-configured providers and models; it does not collect new API keys.

## Diagnostics

```bash
hermes doctor
```

For the API-key path, the doctor checks:

- Whether `GOOGLE_API_KEY` or `GEMINI_API_KEY` is available
- Whether configured provider credentials can be resolved

For the official CLI path, Hermes verifies that `gemini` is available. This is a structural check only; to repair an expired or missing login, run `gemini` interactively and sign in again.

## Gateway (Messaging Platforms)

Gemini works with all Hermes gateway platforms (Telegram, Discord, Slack, WhatsApp, LINE, Feishu, etc.). Configure Gemini as your provider, then start the gateway normally:

```bash
hermes gateway setup
hermes gateway start
```

The gateway reads `config.yaml` and uses the same Gemini provider configuration. For `google-gemini-cli`, the `gemini` executable and its authenticated user profile must exist on the machine running the Hermes backend, not merely on a remote messaging client.

## Troubleshooting

### "Could not find the official Gemini CLI command 'gemini'"

Install the official CLI on the Hermes backend, authenticate it, and retry:

```bash
npm install -g @google/gemini-cli
gemini
# Choose "Sign in with Google"
```

### Gemini CLI reports an authentication or credential error

Run `gemini` interactively on the same backend account and choose **Sign in with Google**. Hermes intentionally does not open the OAuth flow or inspect the CLI's stored credentials from a headless agent request.

### "Gemini native client requires an API key"

Hermes could not find a usable API key. Add one of these to `~/.hermes/.env`:

```bash
GOOGLE_API_KEY=...
# or
GEMINI_API_KEY=...
```

Then run `hermes model` again.

### "This Google API key is on the free tier"

Hermes probes Gemini API keys during setup. Free-tier quotas can be exhausted after a handful of agent turns because tool use, retries, compression, and auxiliary tasks may require multiple model calls.

Enable billing on the Google Cloud project attached to your key, regenerate the key if needed, then run:

```bash
hermes model
```

### "404 model not found"

The selected model is not available for your account, region, or key. Run `hermes model` again and pick another Gemini model from the current list.

### Gemma model is not shown in `hermes model`

Hermes may hide low-throughput Gemma models from the picker by default. If you intentionally want to evaluate one, set the model ID directly in `~/.hermes/config.yaml`.

### "429 quota exceeded" on Gemma

Gemma models exposed through the Gemini API are useful for evaluation, but their Gemini API free-tier caps are low. Use them for compatibility testing, then switch to a paid Gemini model or another provider for sustained agent sessions.

### OpenAI-compatible endpoint is configured

Check `~/.hermes/.env` for:

```bash
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

Change it to the native endpoint or remove the override:

```bash
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

### Tool calling fails with schema errors

Upgrade Hermes and rerun `hermes model`. The native Gemini adapter sanitizes tool schemas for Gemini's stricter function-declaration format; older builds or custom endpoints may not.

## Related

- [AI Providers](/integrations/providers)
- [Configuration](/user-guide/configuration)
- [Fallback Providers](/user-guide/features/fallback-providers)
- [AWS Bedrock](/guides/aws-bedrock) — native cloud-provider integration using AWS credentials
