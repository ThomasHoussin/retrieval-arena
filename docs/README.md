# PDF Corpus

Place your PDF documents in this directory. They will be parsed, chunked, and indexed by the tools in `tools/`.

PDF files are excluded from git (see `.gitignore`). You must provide your own documents.

## Example corpus (D&D 5e)

The benchmark questions in `questions.json` are designed for a D&D 5th Edition corpus. To reproduce the benchmark, you can use:

- [Systems Reference Document (SRD) 5.2.1](https://www.dndbeyond.com/resources/1781-systems-reference-document-srd) — free, Creative Commons
- Free adventures from D&D Beyond or the DMs Guild

Subdirectories are supported — the indexer scans `docs/` recursively.
