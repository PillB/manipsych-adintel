"""Utility to clean ad body text by stripping category/ID suffixes.

The ad_manifest.jsonl body_redacted field often contains:
  "<ad text> - <category> - <id>"
  e.g. "busco señoritas... - Otros - 444939"
       "Se brinda ayuda... - Hombre busca Mujer - 1335046"

This module provides clean_body() to strip the suffix and return only the
ad text. It also provides clean_body_preview() for truncated previews.

CRITICAL: This must be used BEFORE feeding text to any model (TF-IDF,
profile scoring, outlier detection, clustering, authorship) to prevent
suffix metadata from contaminating the feature space.
"""

from __future__ import annotations

import re

# Pattern: " - <category> - <id_or_phone>"
# Category can be: "Otros", "Hombre busca Mujer", "Mujer busca Hombre", etc.
# ID can be: numeric, [REDACTED_PHONE], [REDACTED_EMAIL], etc.
_SUFFIX_PATTERN = re.compile(
    r'\s*[-–—]\s*'  # separator: dash (various forms) with optional spaces
    r'('
    r'(?:Otros|Hombre\s+busca\s+Mujer|Mujer\s+busca\s+Hombre|'
    r'Trabajo|Servicios|Venta|Alquiler|Contactos|'
    r'[A-Z][a-z]+\s+(?:busca|para|en)|'
    r'\[REDACTED_\w+\])'
    r')'
    r'\s*[-–—]\s*'
    r'(\d+|\[REDACTED_\w+\]|.+)?\s*$',
    re.IGNORECASE
)


def clean_body(body_redacted: str) -> str:
    """Strip the ' - Category - ID' suffix from body text.

    Returns only the ad text portion. If no suffix is detected, returns
    the original text unchanged.
    """
    if not body_redacted:
        return ""
    text = body_redacted.strip()
    # Try the regex pattern first
    m = _SUFFIX_PATTERN.search(text)
    if m:
        return text[:m.start()].strip()
    # Fallback: if text ends with " - <digits>" or " - [REDACTED_*]",
    # strip the last " - ..." segment
    parts = text.rsplit(' - ', 2)
    if len(parts) >= 3:
        # Check if the last part looks like an ID (digits or redacted)
        last = parts[-1].strip()
        if last.isdigit() or last.startswith('[REDACTED'):
            return parts[0].strip()
    elif len(parts) == 2:
        last = parts[-1].strip()
        if last.isdigit() or last.startswith('[REDACTED'):
            # Only strip if the remaining text is substantial
            if len(parts[0].strip()) > 20:
                return parts[0].strip()
    return text


def clean_body_preview(body_redacted: str, max_chars: int = 200) -> str:
    """Clean the body text, then truncate to max_chars with ellipsis.

    Cleans the suffix first, then truncates the clean text so the
    truncation never falls in the middle of the suffix.
    """
    clean = clean_body(body_redacted)
    if len(clean) <= max_chars:
        return clean
    # Truncate at word boundary
    truncated = clean[:max_chars]
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.7:  # only cut at word boundary if reasonable
        truncated = truncated[:last_space]
    return truncated + '…'


def clean_ad_text(title: str, body_redacted: str) -> str:
    """Construct the clean ad text (title + clean body) for model input.

    This is the function that should be used by ALL pipeline scripts
    instead of f"{title} {body_redacted}" — it strips the suffix
    metadata BEFORE the text reaches any TF-IDF vectorizer, profile
    scorer, outlier detector, or authorship analyzer.
    """
    clean = clean_body(body_redacted)
    if title and clean:
        return f"{title} {clean}"
    return clean or title or ""


def clean_title_body(title: str, body_redacted: str) -> str:
    """Combine title and clean body into a single display string.

    Some records have the title prepended to the body in body_redacted.
    This function deduplicates if the title is already at the start.
    """
    clean = clean_body(body_redacted)
    if title and clean.lower().startswith(title.lower()):
        return clean  # title is already included
    if title and clean:
        return f"{title} — {clean}"
    return clean or title or ""
