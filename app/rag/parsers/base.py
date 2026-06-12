from dataclasses import dataclass, field


class ParserError(Exception):
    """Raised when a document source cannot be parsed."""


@dataclass
class ParsedDocument:
    text: str
    metadata: dict = field(default_factory=dict)
