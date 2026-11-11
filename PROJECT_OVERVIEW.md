# Tritobol project overview

## Short description

Tritobol is a local-first Python and CLI preprocessor that deterministically
removes redundant prompt material, counts tokens with a selected tokenizer,
and can keep the newest context within a hard token budget. It cleans and
selectively compresses; it does not summarize or rewrite content.

## Long description

Tritobol is designed for developers who want to inspect and control prompt
preprocessing inside their own workflows. It provides a Python API and CLI for
single inputs and local project files, with readable token statistics and
segment reports. Cleanup includes repeated material and formatting noise;
supported Python and JSON blocks can be compressed conservatively and validated
before changes are kept. Local secret-pattern scanning can protect or mask
recognized values.

Token counting uses the bundled DeepSeek V4.1 Flash tokenizer by default.
Callers can instead load a compatible local Hugging Face `tokenizer.json` or
provide an object implementing Tritobol's `Tokenizer` protocol. Counts apply to
the supplied text, not provider-specific chat templates, tools, message
framing, or API overhead. Selecting a tokenizer does not connect Tritobol to
that model provider or automatically integrate its API.

## Market context and problem

Long prompts can contain repeated or low-value material, while model requests
have finite context budgets and may incur usage-based costs. Research also
shows that model performance on some long-context tasks can depend on where
relevant information appears; this is a motivation to treat long-context
handling carefully, not evidence that any particular compression tool
improves model accuracy.

As a commercial market estimate, Grand View Research reports that the global
generative AI market was valued at **$22.2 billion in 2025**, estimates
**$29.6 billion for 2026**, and forecasts **$324.7 billion by 2033**. The 2026
and 2033 values are estimates/forecasts, not observed outcomes. Market size
alone does not establish demand for Tritobol or predict its adoption.

## Tritobol's solution

Tritobol offers a local preprocessing step that:

- removes repeated content and selected whitespace or separator noise without
  semantic summarization or rewriting;
- reports token counts using the bundled tokenizer or a caller-selected local
  tokenizer;
- optionally enforces a hard token limit by retaining the newest token window
  if cleanup alone is insufficient; and
- exposes the same core workflow through Python and the command line, without
  network requests during local processing.

The default tokenizer remains DeepSeek. Other tokenizer support is explicit:
the caller must supply a compatible local tokenizer file or implementation.
Tritobol does not automatically select a model's tokenizer, call model APIs, or
account for request-side overhead.

## Unique functions and positioning vs. TwoTrim

This is a comparison of documented scope, not a claim that one project is
universally better or produces greater savings.

| Area | Tritobol | TwoTrim (as described in its public README) |
| --- | --- | --- |
| Core approach | Deterministic cleanup and duplicate removal; no summarization or semantic rewriting. | Describes extractive/semantic scoring, compression modes, and document reordering. |
| Token counting | Bundled DeepSeek tokenizer by default; optional compatible local Hugging Face tokenizer JSON or custom `Tokenizer` protocol. | Describes OpenAI-compatible proxy and SDK paths; provider routing through LiteLLM is also described. |
| Budget behavior | Optional hard limit retains a tail window of the input. | Describes selectable `lossless`, `balanced`, and `aggressive` modes. |
| Integration surface | Local Python API and CLI; no provider API proxy or automatic provider integration. | README describes a proxy, native SDK, and an OpenAI-format workflow. |

Tritobol's documented distinction is a small, local-first cleanup/counting
library with an explicit tokenizer interface and tail-window budget behavior.
TwoTrim's README presents a broader middleware-style integration and
semantic/extractive compression approach. Any performance or accuracy
comparison would require independent, task-specific evaluation; TwoTrim's
performance figures and integration descriptions above are its own README
claims, not independently verified here.

## Sources

Sources checked **November 2, 2026**:

1. Grand View Research, [Generative AI Market (2026–2033)](https://www.grandviewresearch.com/industry-analysis/generative-ai-market-report).
   The reported 2025 market value and 2026/2033 estimates are commercial market
   research figures.
2. TwoTrim, [public repository README](https://github.com/overseek944/twotrim).
   Product capabilities and performance statements are attributed to that
   project's README.
3. Nelson F. Liu et al., [“Lost in the Middle: How Language Models Use Long Contexts”](https://arxiv.org/abs/2307.03172),
   2023. Reports that performance on studied long-context tasks can vary with
   the position of relevant information.
4. Tritobol, [README](README.md) and current source files. These describe the
   implementation and its limitations summarized above.
