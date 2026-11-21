# SME Loan Copilot

SME Loan Copilot helps loan advisors prepare SME loan applications. Upload a company's annual reports and bank statements; it extracts the figures, analyses cash flow, finds similar past cases and the lenders that approved them, and drafts a cited loan memo. Every number is computed in code and verified, and the advisor makes every decision.

> Work in progress. See [docs/spec.md](docs/spec.md).

## Quickstart

```bash
cp .env.example .env   # add your ANTHROPIC_API_KEY
docker compose up -d
make setup
make dev               # http://localhost:3000
```

## License

MIT
