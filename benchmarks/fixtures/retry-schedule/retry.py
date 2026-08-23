def retry_delays(attempts: int, base_seconds: int = 1) -> list[int]:
    """Return exponential delays between a fixed number of attempts."""

    if attempts < 1:
        raise ValueError("attempts must be positive")
    if base_seconds < 1:
        raise ValueError("base_seconds must be positive")
    return [base_seconds * 2**index for index in range(attempts)]
