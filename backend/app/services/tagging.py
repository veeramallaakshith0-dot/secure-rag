import re

_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,31}$")
MAX_TAGS = 8


def normalize_tag(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    tag = value.strip().casefold()
    if not _TAG_PATTERN.fullmatch(tag):
        raise ValueError("Tags must be 1–32 characters and use only letters, numbers, spaces, hyphens, or underscores")
    return tag


def parse_tags(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    tags = []
    for item in value.split(","):
        tag = normalize_tag(item)
        if tag and tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"A document can have at most {MAX_TAGS} tags")
    return tags
