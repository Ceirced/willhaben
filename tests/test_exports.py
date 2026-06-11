import willhaben


def test_new_public_surface() -> None:
    # every advertised name resolves
    for name in willhaben.__all__:
        assert hasattr(willhaben, name), name
    # the new vertical/order surface is advertised
    for name in ["navigate", "Order", "Vertical", "MARKETPLACE", "REALESTATE", "AUTO",
                 "search", "count", "iter_ads", "NodeView"]:
        assert name in willhaben.__all__, name


def test_removed_symbols_gone() -> None:
    for name in [
        "search_realestate", "count_realestate", "iter_realestate_ads",
        "RealEstateAd", "RealEstateCategory", "EstateMiscCategory",
        "OfferType", "RealEstateSearchResult",
    ]:
        assert not hasattr(willhaben, name), name
