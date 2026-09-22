# Protocol reference

## Authentication

When an API key is configured (one is generated automatically on first start),
every request must present it either as a bearer token or as `x-api-key`:

```
Authorization: Bearer sk-dq0-...
x-api-key: sk-dq0-...
```

`GET /v1/models` and all `POST` endpoints are authenticated. `OPTIONS` is not.

## OpenAI Chat Completions

`POST /v1/chat/completions`

- `model` — requested model id (`deepseek-v4-flash`, `deepseek-v4-pro`,
  `deepseek-vision`, or anything in the configured catalog).
- `messages` — standard role/content array. `content` may be a string or a part
  array; `text`, `input_text`, `output_text`, `tool_use` and `tool_result` parts
  are flattened into the prompt.
- `stream` — when true, responds with `text/event-stream`.
- `max_tokens` / `max_completion_tokens` — output budget.
- `reasoning` (`{ "effort": "..." }` or boolean) or `thinking` — enables the
  reasoning pass.
- `web_search` / `search` — requests the search tool.

Non-streaming responses use the usual `chat.completion` envelope and include
`reasoning_content` on the message when reasoning was produced. Streaming
responses emit `chat.completion.chunk` frames, then `data: [DONE]`.

## OpenAI Responses

`POST /v1/responses`

- `input` — a string, or an array of message objects.
- `instructions` — prepended as a system message.
- `previous_response_id` — passed through for continuation.
- `max_output_tokens` — output budget.
- `stream` — emits `response.created`, `response.output_text.delta`,
  `response.reasoning_summary_text.delta` and `response.completed`.

Codex custom providers should point `base_url` at the printed root and use the
Responses wire API.

## Anthropic Messages

`POST /v1/messages`

- `system` — string or part array.
- `messages` — role/content array; `thinking` parts are preserved.
- `thinking` — `{ "type": "enabled" }` or `{ "type": "adaptive" }` enables the
  reasoning pass.
- `metadata.user_id` — used as the client session scope.
- `stream` — emits `message_start`, `content_block_delta`
  (`text_delta` / `thinking_delta`), `message_delta` and `message_stop`.

`POST /v1/messages/count_tokens` returns `{ "input_tokens": N }`.

Claude Code should set `ANTHROPIC_BASE_URL` to the printed root and
`ANTHROPIC_AUTH_TOKEN` to the API key.

## Protocol selection

The server serves one protocol family at a time. Calling an OpenAI route while
Anthropic mode is selected returns `protocol_mismatch`, and vice versa. Switch
modes from the module UI or by writing `protocol` to the `dq0_local_api`
preferences file.
