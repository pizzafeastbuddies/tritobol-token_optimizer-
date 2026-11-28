# Bundled tokenizer

`deepseek_v41_tokenizer.json` is the tokenizer shipped with
[`deepseek-ai/DeepSeek-V4.1-Flash`](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash).

- Source: `deepseek-ai/DeepSeek-V4.1-Flash`, `tokenizer.json`
- Vocabulary size: 129,280
- License: MIT, Copyright (c) 2023 DeepSeek (see `LICENSE.deepseek-tokenizer`)

The tokenizer is byte-level BPE and is loaded locally. Text token counts are
identical to the V4.1 `deepseek-recipe` copy; only the image special token
differs (`<｜deepseek_image｜>` in the model checkpoint).

# Bundled name lists

`first_names.txt` and `last_names.txt` hold one capitalized name per line. The
personal-data detector reads them to find `First Last` name pairs. Both lists
are small starter lists written for tests and common names. To add a name, add
a line to the file. They contain no real people's records.
