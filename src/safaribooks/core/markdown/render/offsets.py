"""Per-chapter start offsets and the rendered-body result container."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ChapterOffset:
    """Start position of a chapter in the rendered body."""

    byte: int
    line: int


@dataclass
class RenderResult:
    """The rendered Markdown body and one start offset per chapter."""

    body: str
    offsets: list[ChapterOffset] = field(default_factory=list)
