"""Authentication: login verification, the deprecated direct-login path, and credential parsing."""

import logging
import warnings

from safaribooks.core.api.connection import ConnectionMixin
from safaribooks.core.constants import PROFILE_URL
from safaribooks.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

_HTTP_OK = 200


class AuthMixin(ConnectionMixin):
    """Session authentication checks and credential parsing."""

    async def check_login(self) -> bool:
        """Verify that the current cookies grant access to the profile page.

        Returns:
        -------
        bool
            ``True`` when the session is valid.

        Raises:
        ------
        AuthenticationError
            When the session cannot access the profile.

        """
        response = await self.get(PROFILE_URL)

        if response.status_code != _HTTP_OK or "/login" in str(response.url):
            raise AuthenticationError("Unable to access profile page -- authentication failed.")

        if 'user_type":"Expired"' in response.text:
            raise AuthenticationError("Account subscription has expired.")

        logger.info("Successfully authenticated.")
        return True

    def do_login(self, email: str, password: str) -> None:
        """Attempt direct email/password login (deprecated).

        O'Reilly has blocked direct credential-based login.  This method
        exists only for backwards compatibility and will always raise a
        deprecation warning directing users to cookie-based auth.
        """
        warnings.warn(
            "Direct email/password login is no longer supported by O'Reilly. "
            "Use cookie-based authentication instead: safaribooks retrieve-cookies",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.warning(
            "do_login() called but direct login is blocked by O'Reilly. "
            "Use cookie-based authentication instead."
        )

    @classmethod
    def parse_cred(cls, cred: str) -> tuple[str, str] | None:
        """Parse an ``email:password`` credential string.

        Returns:
        -------
        tuple[str, str] | None
            ``(email, password)`` on success, ``None`` if the format is invalid.

        """
        if ":" not in cred:
            return None

        sep = cred.index(":")
        email = cred[:sep].strip("'").strip('"')
        if "@" not in email:
            return None

        password = cred[sep + 1 :]
        return email, password
