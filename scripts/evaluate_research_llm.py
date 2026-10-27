"""Evaluate the Phase 3B summary pipeline on the synthetic, hand-annotated set.

Usage (from backend/, with the venv active):
  python ../scripts/evaluate_research_llm.py                  # replay: no network, no cost
  python ../scripts/evaluate_research_llm.py --live           # the provider configured in NZSTATS_LLM_*

Replay feeds hand-written simulated outputs through parsing, verification and the metrics, so it tests the
deterministic layers, not a model. --live sends the synthetic documents (never third-party text) to the
configured provider, which costs money: run it deliberately and record the model and prompt version.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from nzstats.research.evaluate import EvalBudget, EvalBudgetExceeded, load_eval_set, run_eval  # noqa: E402
from nzstats.research.prompt import PROMPT_VERSION  # noqa: E402
from nzstats.research.providers import build_provider, load_llm_settings  # noqa: E402
from nzstats.research.verify import VERIFIER_VERSION  # noqa: E402

DEFAULT_SET = ROOT / "backend" / "tests" / "research" / "eval_set"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, help="directory of case files")
    parser.add_argument(
        "--live", action="store_true", help="use the configured provider (costs money)"
    )
    args = parser.parse_args()
    cases = load_eval_set(args.set)
    provider, budget = None, None
    if args.live:
        settings = load_llm_settings(os.environ)
        if settings.provider == "disabled":
            print("--live needs NZSTATS_LLM_PROVIDER and the related variables")
            return 1
        provider = build_provider(settings)
        budget = EvalBudget(settings.pricing, settings.limits)
    try:
        report = run_eval(cases, provider=provider, budget=budget)
    except EvalBudgetExceeded as exc:
        spent = f"${budget.spent_usd:.4f}" if budget else "$0"
        print(
            f"stopped: {exc}. Spent {spent}; raise NZSTATS_LLM_MAX_RUN_USD to evaluate the whole set."
        )
        return 1
    model = f"{provider.name}/{provider.model}" if provider else "replay"
    print(
        f"{len(cases)} cases, {len(report.models)} model outputs, {len(report.probes)} probes;"
        f" {model}, prompt {PROMPT_VERSION}, verifier {VERIFIER_VERSION}\n"
    )
    print(report.to_markdown())
    if budget is not None:
        print(f"\nspent ${budget.spent_usd:.4f} of ${budget.limits.max_run_usd:.2f}")
    return 0 if all(p.as_expected for p in report.probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
