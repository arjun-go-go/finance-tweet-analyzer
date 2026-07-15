from uuid import UUID


def normalize_user_id(user_id: str | UUID) -> str:
    """Return the canonical UUID string for an authenticated user identity."""
    if isinstance(user_id, bool) or not isinstance(user_id, (str, UUID)):
        raise ValueError("Authenticated user identity must be a UUID")
    try:
        return str(user_id if isinstance(user_id, UUID) else UUID(user_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Authenticated user identity must be a UUID") from exc
