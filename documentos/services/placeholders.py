import re
from typing import Iterable
from typing import Mapping

from .exceptions import DocumentValidationError
from .exceptions import UnresolvedPlaceholderError


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def extract_placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(text))


def ensure_required_placeholders(
    payload: Mapping[str, object],
    required_placeholders: Iterable[str],
) -> None:
    missing = [key for key in required_placeholders if key not in payload]
    if missing:
        ordered = ", ".join(sorted(missing))
        raise DocumentValidationError(f"Placeholders obrigatórios ausentes no payload: {ordered}")


def find_unresolved_placeholders(text: str) -> set[str]:
    return extract_placeholders(text)


def ensure_no_unresolved_placeholders(text: str) -> None:
    unresolved = find_unresolved_placeholders(text)
    if unresolved:
        ordered = ", ".join(sorted(unresolved))
        raise UnresolvedPlaceholderError(f"Placeholders não resolvidos: {ordered}")


def render_template_content(template_content: str, payload: Mapping[str, object]) -> str:
    rendered = template_content
    for key, value in payload.items():
        rendered = re.sub(
            rf"\{{\{{\s*{re.escape(key)}\s*\}}\}}",
            str(value),
            rendered,
        )
    return rendered
