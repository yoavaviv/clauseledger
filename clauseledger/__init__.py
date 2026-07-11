"""ClauseLedger: a reliability harness for contract-obligation extraction.

Not "another contract AI". It measures how often an extractor silently misses or
fabricates obligations, recovers the misses with an adversarial coverage pass,
abstains instead of guessing, and publishes honest numbers under fault injection.
"""
__version__ = "0.1.0"

from .schema import CLAUSE_TYPES  # noqa: F401
