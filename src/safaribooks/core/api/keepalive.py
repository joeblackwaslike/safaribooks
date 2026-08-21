"""Background session keepalive: periodic pings to the profile endpoint."""

import asyncio
import contextlib
import logging

from safaribooks.core.api.connection import ConnectionMixin
from safaribooks.core.constants import PROFILE_URL

logger = logging.getLogger(__name__)


class KeepaliveMixin(ConnectionMixin):
    """Starts and stops a background task that keeps the session alive."""

    async def start_keepalive(self) -> None:
        """Start a background task that pings the profile endpoint periodically."""
        interval = self.config.keepalive_interval
        if interval <= 0:
            return
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(interval))
        logger.debug("Session keepalive started (every %ds).", interval)

    async def stop_keepalive(self) -> None:
        """Cancel the keepalive background task if running."""
        task = self._keepalive_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            logger.debug("Session keepalive stopped.")

    async def _keepalive_loop(self, interval: int) -> None:
        """Periodically hit the profile endpoint to extend the session."""
        while True:
            await asyncio.sleep(interval)
            try:
                await self.get(PROFILE_URL, update_cookies=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Keepalive ping failed: %s", exc)
            else:
                logger.debug("Keepalive ping OK.")
