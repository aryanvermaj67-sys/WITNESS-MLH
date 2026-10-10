"""Answer writer: Gemma 4 E2B through LM Studio's OpenAI-compatible API (FR-3, prompt §9.1)."""
import openai
from openai import OpenAI

from witness.config import settings
from witness.models import Passage

SYSTEM = "Answer the question using only the passages. Write 3 to 5 short sentences. Do not add citations or lists."
TIMEOUT = 20  # seconds (§5 rule 7)


def build_user(question: str, passages: list[Passage]) -> str:
    blocks = "\n".join(f"[{p.id}] {p.text}" for p in passages)
    return f"{blocks}\n\nQuestion: {question}"


def generate(question: str, passages: list[Passage], client: OpenAI | None = None) -> tuple[str, str | None]:
    """(answer, error). Never raises: any failure is ("", readable message)."""
    try:
        client = client or OpenAI(base_url=settings.LMSTUDIO_BASE_URL, api_key="lm-studio", timeout=TIMEOUT, max_retries=0)
        reply = client.chat.completions.create(
            model=settings.LMSTUDIO_MODEL,
            temperature=settings.GEN_TEMPERATURE,
            max_tokens=settings.GEN_MAX_TOKENS,
            # Gemma 4 E2B is a reasoning model: without this it spends all its tokens thinking and returns nothing
            extra_body={"reasoning_effort": "none"},
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_user(question, passages)}],
        )
        answer = " ".join((reply.choices[0].message.content or "").split())
    except openai.APITimeoutError:
        return "", (f"LM Studio did not answer within {TIMEOUT} s (the model may still be loading). "
                    "Try again, or paste an answer in Grade any AI.")
    except openai.APIStatusError as e:
        return "", (f"LM Studio returned an error (HTTP {e.status_code}). "
                    f"Check that {settings.LMSTUDIO_MODEL or 'the model'} is loaded, or paste an answer in Grade any AI.")
    except Exception:
        return "", (f"LM Studio is not reachable at {settings.LMSTUDIO_BASE_URL}. "
                    "Start the LM Studio local server or paste an answer in Grade any AI.")
    if not answer:
        return "", "The answer writer returned an empty answer. Try again or paste an answer in Grade any AI."
    return answer, None
