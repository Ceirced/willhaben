from __future__ import annotations

import pytest

from willhaben import count


@pytest.mark.live
def test_live_count_returns_positive() -> None:
    """Smoke test: keyword 'fahrrad' should always have results on willhaben.at."""
    assert count(keyword="fahrrad") > 0
