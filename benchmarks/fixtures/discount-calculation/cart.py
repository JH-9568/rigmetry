def discounted_total(subtotal: int, percent: int) -> int:
    """Apply an integer percentage discount using floor arithmetic."""

    if subtotal < 0:
        raise ValueError("subtotal must be non-negative")
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return subtotal - (subtotal * percent // 10)
