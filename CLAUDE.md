# Project context for AI assistants

IEEE RAG Hackathon (Bethlehem University) entry. Judging guide summary: RAG quality 30, problem fit 15,
code quality 15, business 15, marketing 10, pitch 10, innovation 5, +10 bonus for a working product
(bonus only if RAG score >= 15/30). Tie-breakers: RAG score, then evaluation score.

## Layout
- `backend/` FastAPI + ChromaDB + BM25 hybrid + fastembed (multilingual-e5-large, jina reranker v2) + OpenRouter.
  - Problem-specific config: `backend/config/domain.yaml` (persona, prompt extras, refusal, samples, RBAC).
  - Tunables: `.env` (see `.env.example`). Docs to index: `backend/data/raw/<category>/`.
  - Eval set: `backend/data/eval/eval_set.json`; run `make eval-fast` / `make eval TAG=x`.
  - Pipeline: ingestion/{loaders,arabic,chunker,pipeline} -> retrieval/{embeddings,vectorstore,reranker,retriever}
    -> generation/{llm,prompts,generator} -> api/routes_*.
- `frontend/` Next.js 16 (App Router, client components) + Tailwind v4 + shadcn/ui (hand-written in
  `src/components/ui`) + AntV G2 charts. RTL Arabic by default. Read `frontend/AGENTS.md` before touching Next APIs.
- UI design follows the project skill `.claude/skills/frontend-design` with the **Swiss** anchor:
  white surface, one family (IBM Plex Sans Arabic), one accent Yves Klein Blue #002FA7, hairline rules,
  square corners, no shadows, light mode only. Differentiator: "folio citations" (`.folio` class).
  Keep new UI inside those tokens; all on-screen strings go through `src/lib/i18n.ts`.
- `docs/` hackathon-day playbook, per-problem playbooks, judge Q&A, business/marketing/pitch templates.

## Commands
`make setup | models | check | reset | eval-fast | eval | dev | test | lint | cost`

## Rules
- Never commit `.env` or API keys. Keep the AI-usage disclosure in README accurate.
- Every business number needs a cited source or an explicit "assumption" label.
- Tests use `EMBEDDING_PROVIDER=hash` and a fake LLM (see `backend/tests/conftest.py`).
