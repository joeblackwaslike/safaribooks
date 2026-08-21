"""Authentication-cookie Pydantic models for safaribooks."""

from collections.abc import Mapping
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from safaribooks.core.constants import REQUIRED_COOKIES


class CookieSet(BaseModel):
    """Validated set of O'Reilly authentication cookies.

    Instances are frozen and their ``cookies`` mapping is read-only, so the
    "required cookies present" invariant can't be broken by attribute
    reassignment or in-place mutation after construction. Pydantic v2's
    ``model_copy(update=...)`` skips validation entirely (documented
    behavior), so it can still bypass this invariant -- always construct
    instances via ``CookieSet(cookies=...)`` or ``CookieSet.model_validate(...)``,
    never ``model_copy(update=...)``.
    """

    model_config = ConfigDict(frozen=True)

    cookies: Mapping[str, str]

    @field_validator("cookies", mode="after")
    @classmethod
    def _freeze_cookies(cls, cookies: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(cookies))

    @model_validator(mode="after")
    def _check_required_cookies(self) -> "CookieSet":
        missing = REQUIRED_COOKIES - self.cookies.keys()
        if missing:
            missing_names = ", ".join(sorted(missing))
            msg = f"Missing required cookies: {missing_names}"
            raise ValueError(msg)
        return self
