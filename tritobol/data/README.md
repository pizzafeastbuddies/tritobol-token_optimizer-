# Bundled tokenizer

`deepseek_v41_tokenizer.json` is the tokenizer shipped with
[`deepseek-ai/DeepSeek-V4.1-Flash`](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash).

- Source: `deepseek-ai/DeepSeek-V4.1-Flash`, `tokenizer.json`
- Vocabulary size: 129,280
- License: MIT, Copyright (c) 2023 DeepSeek (see `LICENSE.deepseek-tokenizer`)

The tokenizer is byte-level BPE and is loaded locally. Text token counts are
identical to the V4.1 `deepseek-recipe` copy; only the image special token
differs (`<｜deepseek_image｜>` in the model checkpoint).
