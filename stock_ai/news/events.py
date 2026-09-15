from __future__ import annotations

import re


EVENT_CATEGORIES = [
    "EARNINGS_BEAT",
    "EARNINGS_MISS",
    "GUIDANCE_RAISED",
    "GUIDANCE_LOWERED",
    "ANALYST_UPGRADE",
    "ANALYST_DOWNGRADE",
    "PARTNERSHIP",
    "ACQUISITION",
    "MERGER",
    "PRODUCT_LAUNCH",
    "NEW_CONTRACT",
    "REGULATORY_APPROVAL",
    "REGULATORY_RISK",
    "LAWSUIT",
    "EXECUTIVE_CHANGE",
    "LAYOFF",
    "FINANCING",
    "STOCK_OFFERING",
    "SHARE_BUYBACK",
    "DIVIDEND",
    "CUSTOMER_WIN",
    "GENERAL_NEWS",
]

EVENT_RULES: list[tuple[str, list[str]]] = [
    ("EARNINGS_BEAT", [r"\bbeats? earnings\b", r"\beats? estimates\b", r"\bearnings beat\b"]),
    ("EARNINGS_MISS", [r"\bmiss(?:es)? earnings\b", r"\bmiss(?:es)? estimates\b", r"\bearnings miss\b"]),
    ("GUIDANCE_RAISED", [r"\braises? guidance\b", r"\blifts? guidance\b", r"\bboosts? outlook\b"]),
    ("GUIDANCE_LOWERED", [r"\bcuts? guidance\b", r"\blowers? guidance\b", r"\breduces? outlook\b"]),
    ("ANALYST_UPGRADE", [r"\bupgrad(?:e|ed|es)\b", r"\braised to buy\b"]),
    ("ANALYST_DOWNGRADE", [r"\bdowngrad(?:e|ed|es)\b", r"\blowered to sell\b"]),
    ("PARTNERSHIP", [r"\bpartner(?:s|ship)\b", r"\bcollaboration\b"]),
    ("ACQUISITION", [r"\bacquir(?:e|es|ed|ing)\b", r"\bacquisition\b"]),
    ("MERGER", [r"\bmerger\b", r"\bmerges?\b"]),
    ("PRODUCT_LAUNCH", [r"\blaunch(?:es|ed)?\b", r"\bunveils?\b", r"\bnew product\b"]),
    ("NEW_CONTRACT", [r"\bwins? contract\b", r"\bnew contract\b", r"\bcontract award\b"]),
    ("REGULATORY_APPROVAL", [r"\bregulatory approval\b", r"\bfda approves?\b", r"\bapproved by regulators\b"]),
    ("REGULATORY_RISK", [r"\bregulatory risk\b", r"\bprobe\b", r"\binvestigation\b"]),
    ("LAWSUIT", [r"\blawsuit\b", r"\bsues?\b", r"\bsettlement\b"]),
    ("EXECUTIVE_CHANGE", [r"\bceo\b", r"\bcfo\b", r"\bexecutive\b", r"\bsteps down\b"]),
    ("LAYOFF", [r"\blayoffs?\b", r"\bcuts jobs\b", r"\bworkforce reduction\b"]),
    ("FINANCING", [r"\bfinancing\b", r"\braises capital\b", r"\bdebt offering\b"]),
    ("STOCK_OFFERING", [r"\bstock offering\b", r"\bshare offering\b", r"\bpublic offering\b"]),
    ("SHARE_BUYBACK", [r"\bbuyback\b", r"\brepurchase\b"]),
    ("DIVIDEND", [r"\bdividend\b"]),
    ("CUSTOMER_WIN", [r"\bcustomer win\b", r"\badds customer\b", r"\bselected by\b"]),
]


def categorize_event(headline: str, summary: str | None = None) -> str:
    text = f"{headline} {summary or ''}".lower()
    for category, patterns in EVENT_RULES:
        if any(re.search(pattern, text) for pattern in patterns):
            return category
    return "GENERAL_NEWS"

