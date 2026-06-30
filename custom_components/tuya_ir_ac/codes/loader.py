"""Loading and merging of built-in and user-learned IR code tables."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .schema import CodeTable, validate_code_table

_LOGGER = logging.getLogger(__name__)

CODES_DIR = Path(__file__).parent


def list_variants(brand: str) -> list[str]:
    """Return the built-in variant names available for a brand."""
    brand_dir = CODES_DIR / brand
    if not brand_dir.is_dir():
        return []
    return sorted(path.stem for path in brand_dir.glob("*.json"))


def load_builtin_codeset(brand: str, variant: str) -> CodeTable:
    """Load and validate a bundled brand/variant code table."""
    path = CODES_DIR / brand / f"{variant}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No built-in code table for {brand}/{variant}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_code_table(data, source=str(path))


def get_merged_table(builtin: CodeTable, learned: dict[str, str]) -> dict[str, str]:
    """Merge a built-in code table with user-learned overrides.

    Learned codes always take precedence over built-in ones, since they are
    captured from the user's actual remote and are the reliability fallback
    for built-in tables that don't match their exact AC model.
    """
    return {**builtin.codes, **learned}
