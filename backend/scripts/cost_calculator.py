"""Unit-economics calculator for the business plan (cost per answer, per user, break-even).

    python -m scripts.cost_calculator --users 10000 --q-per-user 20 --price 3
All assumptions are printed so you can put them on the slide.
"""

import argparse

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=10_000, help="monthly active users")
    ap.add_argument("--q-per-user", type=float, default=20, help="questions per user per month")
    ap.add_argument("--prompt-tokens", type=int, default=2500, help="avg prompt tokens (system+5 chunks+question)")
    ap.add_argument("--completion-tokens", type=int, default=350)
    ap.add_argument("--rewrite-tokens", type=int, default=400, help="query-rewrite call tokens")
    ap.add_argument("--hosting", type=float, default=60, help="USD/month server (CPU VM for API+Chroma+embeddings)")
    ap.add_argument("--team", type=float, default=0, help="USD/month salaries (0 for student team)")
    ap.add_argument("--price", type=float, default=3.0, help="USD per paying user per month")
    ap.add_argument("--paying-share", type=float, default=0.05, help="free->paid conversion")
    a = ap.parse_args()

    per_answer = s.cost_usd(a.prompt_tokens + a.rewrite_tokens, a.completion_tokens + 80)
    queries = a.users * a.q_per_user
    llm_month = queries * per_answer
    total = llm_month + a.hosting + a.team
    revenue = a.users * a.paying_share * a.price
    print(f"Model: {s.llm_model} (${s.llm_price_input_per_m}/M in, ${s.llm_price_output_per_m}/M out)")
    print(f"Embeddings: local {s.embedding_model} -> $0 per query")
    print(f"Cost per answer         : ${per_answer:.5f}")
    print(f"Queries / month         : {queries:,.0f}")
    print(f"LLM cost / month        : ${llm_month:,.2f}")
    print(f"Total cost / month      : ${total:,.2f}  (hosting ${a.hosting}, team ${a.team})")
    print(f"Cost per active user    : ${total / a.users:.4f}")
    print(f"Revenue / month         : ${revenue:,.2f}  ({a.paying_share:.0%} pay ${a.price})")
    print(f"Gross margin            : {((revenue - total) / revenue * 100) if revenue else 0:.1f}%")
    be_users = total / (a.paying_share * a.price) if a.paying_share * a.price else float('inf')
    print(f"Break-even MAU          : {be_users:,.0f}")
