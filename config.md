# Anki Reflect — Configuration Reference

## `report_scope`
Controls the time window for the session report.
- `"today"` — Reviews made since midnight local time (default)
- `"week"` — Reviews from the last 7 days
- `"month"` — Reviews from the last 30 days

## `mature_threshold_days`
Cards with an interval ≥ this value (in days) are counted as **mature**.
Default: `21` (matches Anki's native stats definition).

## `history_days`
Number of days of history shown in the **Mature Card Growth Plot**.
Default: `90`.

## `graph_theme`
Visual theme for generated graphs.
- `"dark"` — Dark background (recommended for Anki's night mode)
- `"light"` — White background

## `graph_accent_color` / `graph_secondary_color`
Hex colour codes used for the primary and secondary graph series.

## `llm_enabled`
Set to `true` to generate the narrative reflection using an LLM API instead
of the built-in template engine. Requires a valid `llm_api_key`.

## `llm_provider`
Which LLM provider to use when `llm_enabled` is `true`.
- `"openai"` — OpenAI API (gpt-4o-mini, gpt-4o, etc.)
- `"anthropic"` — Anthropic Claude API

## `llm_api_key`
Your API key for the chosen provider. Keep this private — do not share your
Anki profile or this config with others if a key is set here.

## `llm_model`
The model identifier to use. Examples:
- OpenAI: `"gpt-4o-mini"`, `"gpt-4o"`
- Anthropic: `"claude-3-haiku-20240307"`, `"claude-3-5-sonnet-20241022"`

## `deck_filter`
- `"all"` — Include all decks (default)
- Any other value is treated as a deck name prefix to filter by.

## `show_comparison_table` / `show_fsrs_metrics` / `show_growth_graph`
Toggle individual report sections on or off (`true`/`false`).
