"""Time the same grounded question on several free models and print speed + answer.

    make bench
    make bench MODELS="gemini-3.5-flash-lite gemini-3.5-flash"
"""

import sys
import time

from app.generation.llm import get_llm

DEFAULT = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash"]
QUESTION = [
    {"role": "system", "content": "أجب بجملة واحدة بالعربية اعتماداً على المصدر فقط، وضع [1] بعد المعلومة."},
    {"role": "user", "content": "<sources>[1] الحد الأعلى للعبء الدراسي في الفصل العادي هو 18 ساعة معتمدة.</sources>\nالسؤال: كم الحد الأعلى للساعات؟"},
]

if __name__ == "__main__":
    models = sys.argv[1:] or DEFAULT
    llm = get_llm()
    print(f"{'model':28s} {'time':>7s}  answer")
    for m in models:
        t = time.time()
        try:
            r = llm.complete(QUESTION, model=m, max_tokens=300, utility=True)
            print(f"{m:28s} {time.time() - t:6.1f}s  {r.text[:70]!r}")
        except Exception as exc:
            print(f"{m:28s}   ERROR  {str(exc)[:90]}")
    print("\nPick the fastest model that answers correctly for LLM_MODEL in .env.")
