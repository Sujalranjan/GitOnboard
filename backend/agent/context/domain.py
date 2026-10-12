"""Domain concept extraction and architectural classification for ContextAssembler."""

from __future__ import annotations
import re
from typing import List


class DomainIntent(dict):
    """Container for domain concept extraction supporting both dict access and membership checks."""
    def __contains__(self, item):
        if super().__contains__(item):
            return True
        return (
            item in self.get("primary", [])
            or item in self.get("secondary", [])
            or item in self.get("raw_words", [])
        )


def extract_domain_concepts(requirement: str) -> DomainIntent:
    """
    Extracts high-signal primary capability keywords, secondary context keywords,
    and classifies the architectural domain of the requested capability.
    Operates strictly on generic domain terminology without hardcoded repository file names.
    """
    planning_noise = {
        "what", "would", "it", "take", "to", "add", "implement", "feature", "system",
        "please", "could", "should", "want", "need", "like", "about", "into", "make",
        "help", "this", "that", "with", "from", "have", "tell", "show", "give", "step",
        "steps", "plan", "estimate", "changes", "files", "file", "for", "and", "the", "a", "an",
        "require", "require?", "take?", "add?", "create", "setup", "new", "do", "we", "of", "in",
        "how", "can"
    }
    cleaned = re.sub(r"[^\w\s-]", " ", requirement)
    words = [w.lower() for w in cleaned.split() if w.lower() not in planning_noise and len(w) > 1]
    req_lower = requirement.lower()

    primary_kws: List[str] = []
    secondary_kws: List[str] = []
    arch_layer: str = "GENERAL"

    # 1. Auth / Access Control / RBAC / Permissions
    if any(k in req_lower for k in ["role", "rbac", "admin", "permission", "access control", "guard", "oauth", "auth", "login"]):
        primary_kws.extend(["auth", "authentication", "login", "oauth", "jwt", "session", "user", "permission", "role", "guard", "security", "credentials", "middleware", "token"])
        secondary_kws.extend(["user", "session", "permission", "access"])
        arch_layer = "AUTH_ACCESS_CONTROL"
    # 2. Search / Query across data sources
    elif any(k in req_lower for k in ["search", "find", "filter", "lookup", "query", "index"]):
        primary_kws.extend(["search", "query", "find", "filter", "lookup", "index", "browse", "retrieve"])
        secondary_kws.extend(["data", "item", "record", "store"])
        arch_layer = "DATA_SEARCH_QUERY"
    # 3. External Notifications / Messaging (Email, SMS, Webhooks)
    elif any(k in req_lower for k in ["email", "notification", "notify", "sms", "mailer", "webhook", "alert"]):
        primary_kws.extend(["notification", "notify", "email", "mailer", "alert", "message", "webhook", "sms"])
        secondary_kws.extend(["finish", "status", "complete", "event"])
        arch_layer = "EXTERNAL_COMMUNICATIONS"
    # 4. Theming / Styling
    elif any(k in req_lower for k in ["dark", "mode", "theme", "color", "styling"]):
        primary_kws.extend(["theme", "dark", "mode", "color", "style", "palette", "theme-provider"])
        secondary_kws.extend(["style", "color"])
        arch_layer = "THEMING_UI"
    # 5. Pagination / Data fetching
    elif any(k in req_lower for k in ["pagination", "paginate", "page", "cursor"]):
        primary_kws.extend(["pagination", "paginate", "page", "cursor", "limit", "offset"])
        secondary_kws.extend(["users", "user", "fetch", "query"])
        arch_layer = "API_CLIENT_PAGINATION"
    # 6. Payment / Billing
    elif any(k in req_lower for k in ["payment", "stripe", "billing", "checkout"]):
        primary_kws.extend(["payment", "stripe", "billing", "checkout", "subscription", "invoice"])
        arch_layer = "PAYMENTS_BILLING"
    # 7. Server Cache / Infra
    elif any(k in req_lower for k in ["redis", "cache", "caching", "memcached"]):
        primary_kws.extend(["cache", "caching", "redis", "memcached", "store"])
        arch_layer = "SERVER_INFRA"
    else:
        primary_kws.extend(words)

    return DomainIntent(
        primary=primary_kws,
        secondary=secondary_kws,
        arch_layer=arch_layer,
        raw_words=words,
    )
