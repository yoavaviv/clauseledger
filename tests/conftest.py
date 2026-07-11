"""Shared fixtures. A synthetic contract with fully-known spans lets us assert exact
grounding and metric values; the real CUAD subset provides an integration fixture.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clauseledger.cuad import Contract, load_subset  # noqa: E402
from clauseledger.schema import Span  # noqa: E402


SYN_TEXT = (
    "MASTER SERVICES AGREEMENT. "
    "1. This Agreement shall be governed by the laws of the State of Delaware. "
    "2. The initial term is one year and shall automatically renew for successive "
    "one-year periods unless terminated. "
    "3. Either party may prevent renewal by giving ninety (90) days written notice "
    "prior to the end of the then-current term. "
    "4. In no event shall the total liability of either party exceed the fees paid "
    "in the twelve months preceding the claim. "
    "5. Upon termination the Provider shall continue to provide transition services "
    "for sixty (60) days. "
)


def _span(text, needle):
    i = text.find(needle)
    assert i != -1, f"needle not in text: {needle!r}"
    return Span(start=i, end=i + len(needle), text=needle)


@pytest.fixture
def syn_text():
    return SYN_TEXT


@pytest.fixture
def syn_gold():
    t = SYN_TEXT
    return {
        "Governing Law": [_span(t, "governed by the laws of the State of Delaware")],
        "Renewal Term": [_span(t, "automatically renew for successive one-year periods")],
        "Notice Period To Terminate Renewal": [_span(t, "ninety (90) days written notice")],
        "Cap On Liability": [_span(t, "total liability of either party exceed the fees paid")],
        "Liquidated Damages": [],
        "Post-Termination Services": [_span(t, "continue to provide transition services")],
    }


@pytest.fixture
def syn_contract(syn_gold):
    return Contract(id="SYN-1", text=SYN_TEXT, gold=syn_gold,
                    absent=["Liquidated Damages"], split="test")


@pytest.fixture
def stub_from_gold(syn_gold):
    """Build StubBackend initial/recovery dicts that return the real gold quotes,
    so a full pipeline run should score high recall and zero fabrication."""
    from clauseledger.backends import StubBackend
    initial, recovery = {}, {}
    for ct, spans in syn_gold.items():
        if not spans:
            continue
        rows = [{"claim": f"{ct} obligation", "quote": s.text} for s in spans]
        # put Notice Period in recovery to exercise recall lift
        if ct == "Notice Period To Terminate Renewal":
            recovery[("SYN-1", ct)] = rows
        else:
            initial[("SYN-1", ct)] = rows
    return StubBackend(initial=initial, recovery=recovery)


@pytest.fixture(scope="session")
def real_subset():
    return load_subset()
