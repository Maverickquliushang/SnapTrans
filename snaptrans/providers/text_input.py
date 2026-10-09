import re


def translation_input(text):
    """Translate a standalone snake_case UI label as words; preserve other text."""
    stripped = text.strip()
    if re.fullmatch(r'[A-Za-z]+(?:_[A-Za-z]+)+', stripped) and len(stripped) <= 80:
        return stripped.replace('_', ' ')
    return text
