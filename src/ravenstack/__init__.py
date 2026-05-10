"""RavenStack preprocessing package.

Turns the raw CSV exports in ``data/raw/`` into a clean set of
dimension, fact and summary tables in ``data/processed/`` that are
ready to be consumed by Power BI.
"""

from ravenstack.config import PROCESSED_DIR, RAW_DIR

__all__ = ["RAW_DIR", "PROCESSED_DIR"]
