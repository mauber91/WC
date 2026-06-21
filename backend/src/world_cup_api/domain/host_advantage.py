from __future__ import annotations

CO_HOST_COUNTRIES = frozenset({"MX", "US", "CA"})


def venue_home_flags(country_a: str, country_b: str, host_country: str | None) -> tuple[bool, bool]:
    """True when a co-host nation plays in its own host country."""
    if not host_country or host_country not in CO_HOST_COUNTRIES:
        return False, False
    return country_a == host_country, country_b == host_country
