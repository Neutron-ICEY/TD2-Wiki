import re


def is_milestone(item):
    """Identify reward-only equipment by its native internal name, not its display name."""
    return bool(re.search(r'(^|_)milestone(_|$)', item.get('internal_name', ''), re.IGNORECASE))
