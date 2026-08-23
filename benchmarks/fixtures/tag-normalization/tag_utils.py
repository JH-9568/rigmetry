def normalize_tag(value: str) -> str:
    """Return a lowercase, hyphen-separated tag."""

    return value.strip().lower().replace(" ", "-")
