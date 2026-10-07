# Contributing

Thank you for helping improve Bangla FactCheck zkRAG.

## Development setup

1. Fork and clone the repository.
2. Copy `.env.example` to `.env` and add only the credentials needed for your work.
3. Create a Python 3.11+ virtual environment and install `code/requirements.txt`.
4. Run `npm ci` in `bangla-fact-check-main/`, `zk/`, and `blockchain-anchor/` as needed.

Never commit API keys, wallet keys, uploaded documents, claim records, or generated local data.

## Before opening a pull request

Run the checks relevant to your change:

```bash
python -m compileall -q code
cd bangla-fact-check-main && npm run build && npm run lint
cd ../blockchain-anchor && npm test
cd ../zk && sha256sum -c build/SHA256SUMS
```

For ZK changes, also rebuild the affected circuit, record the Circom/snarkjs versions, update checksums, and rerun the benchmark and mutation suite described in `zk/THESIS_EVALUATION_REPORT.md`.

## Pull requests

- Keep changes focused and explain the research or product motivation.
- Add or update tests for behavioral changes.
- Update documentation and figures when claims or measured results change.
- State any API, proof-format, dataset, or migration implications.
- Do not describe cryptographic binding as proof that a news claim is true.
