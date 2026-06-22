"""Authentication-cookie Pydantic models for safaribooks."""

from pydantic import BaseModel, model_validator

from safaribooks.core.constants import REQUIRED_COOKIES


class CookieSet(BaseModel):
    """Validated set of O'Reilly authentication cookies."""

    cookies: dict[str, str]

    @model_validator(mode="after")
    def _check_required_cookies(self) -> "CookieSet":
        missing = REQUIRED_COOKIES - self.cookies.keys()
        if missing:
            missing_names = ", ".join(sorted(missing))
            msg = f"Missing required cookies: {missing_names}"
            raise ValueError(msg)
        return self
