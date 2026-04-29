from __future__ import annotations

import pytest

from willhaben import count


@pytest.mark.live
def test_live_count_returns_positive() -> None:
    """Smoke test: keyword 'fahrrad' should always have results on willhaben.at."""
    assert count(keyword="fahrrad") > 0


from willhaben import REAL_ESTATE_AREAS, RealEstateCategory, count_realestate


@pytest.mark.live
def test_live_realestate_count_returns_positive() -> None:
    """Smoke test: rental flats in Vienna should always have results."""
    result = count_realestate(
        category=RealEstateCategory.APARTMENT_RENT,
        area_id=REAL_ESTATE_AREAS["wien"],
    )
    assert result > 0
