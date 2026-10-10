"""witness-verify: check an answer against the WITNESS knowledge base and print the PipelineResult as JSON.

Usage: verify.py QUESTION [--answer TEXT]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # backend/, so `witness` imports

from witness import judge_nli, pipeline  # noqa: E402
from witness.config import settings  # noqa: E402
from witness.kb import load_kb  # noqa: E402
from witness.retrieval import Retriever, load_embedder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an answer against the WITNESS knowledge base.")
    parser.add_argument("question")
    parser.add_argument("--answer", help="answer to check; without it the local writer model answers first")
    args = parser.parse_args()

    passages, titles = load_kb(settings.path(settings.KB_DIR))
    retriever = Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))
    try:
        nli = judge_nli.load_model(settings.NLI_MODEL, settings.NLI_DEVICE)
    except Exception:  # the result's `errors` then reports the missing NLI judge
        nli = None
    result = pipeline.run_pipeline(args.question.strip(), args.answer, retriever, nli)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
