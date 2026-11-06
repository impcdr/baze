"""Same local replies the Kiln chat uses, persisted by the API."""


def reply_for(prompt: str) -> str:
    text = prompt.lower()
    if "rewrite" in text or "clear" in text:
        return (
            "A clearer version:\n\n"
            "Say the point in one sentence. Then the reason. Then what you want the reader to do.\n\n"
            "Cut any sentence that repeats the one before it. If you paste the original, I can tighten it line by line."
        )
    if "weekend" in text:
        return (
            "A quiet weekend, kept small:\n\n"
            "Saturday morning — a long walk before the town wakes up.\n"
            "Saturday afternoon — one good meal, cooked slowly.\n"
            "Sunday — nothing scheduled past noon.\n\n"
            "Leave one evening empty on purpose."
        )
    if "signal" in text:
        return (
            "Signals are values Angular can watch. You read one by calling it, and the view updates when it changes.\n\n"
            "A computed signal derives from other signals. An effect runs when the signals it reads change — useful at the edges, easy to overuse.\n\n"
            "Prefer computed for anything you show. Keep effects for persistence and other side effects."
        )
    if "note" in text or "draft" in text:
        return (
            "A short note:\n\n"
            "Thanks for the time today. I will send the next version by Friday, and I will flag anything that needs a decision before then."
        )
    subject = " ".join(prompt.split())
    return (
        "Here is a careful take.\n\n"
        f"You asked: “{subject}”\n\n"
        "Start with the outcome you want, then the constraint that matters most, then the first small step. "
        "Tell me which of those is still fuzzy and we can sharpen it."
    )


def title_from(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) > 42:
        return compact[:42].rstrip() + "…"
    return compact
