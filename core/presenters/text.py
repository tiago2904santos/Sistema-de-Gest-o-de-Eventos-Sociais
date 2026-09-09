def join_non_empty(parts, sep=" · ") -> str:
    """Join display fragments without leaving orphan separators."""
    values = []
    for part in parts:
        if part is None:
            continue
        value = str(part).strip()
        if value:
            values.append(value)
    return sep.join(values)
