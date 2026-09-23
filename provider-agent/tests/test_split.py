"""Pure payout arithmetic: no chain, network, keys or agent main loop."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("provider_agent", Path(__file__).parents[1] / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


@pytest.mark.parametrize("uaba", [0, 1, 2, 24, 25, 26, 99, 100, 101, 1_000_000, 2**53 + 1, 10**24 + 99])
def test_split_conserves_micro_units_and_rounds_host_down(uaba):
    parts = agent.split_amount(uaba)
    assert set(parts) == {"host", "stakers", "treasury", "burn"}
    assert all(isinstance(value, int) and value >= 0 for value in parts.values())
    assert sum(parts.values()) == uaba
    # Independent integer bounds for the documented 88% host / 4% legs.
    for key, percent in (("host", 88), ("stakers", 4), ("burn", 4)):
        assert parts[key] * 100 <= uaba * percent < (parts[key] + 1) * 100
    assert parts["treasury"] == uaba - parts["host"] - parts["stakers"] - parts["burn"]


def test_exact_percentages_when_no_rounding_is_needed():
    assert agent.split_amount(100) == {"host": 88, "stakers": 4, "treasury": 4, "burn": 4}
    assert agent.SPLIT == {"host": .88, "stakers": .04, "treasury": .04, "burn": .04}


def test_treasury_retains_the_existing_rounding_remainder():
    assert agent.split_amount(26) == {"host": 22, "stakers": 1, "treasury": 2, "burn": 1}
    assert agent.split_amount(1) == {"host": 0, "stakers": 0, "treasury": 1, "burn": 0}
