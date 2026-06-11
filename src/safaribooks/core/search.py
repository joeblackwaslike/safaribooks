"""Book search via the O'Reilly Learning API."""

import logging
from urllib.parse import quote_plus

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import SEARCH_QUERY_TEMPLATE
from safaribooks.core.exceptions import ApiError, SearchError
from safaribooks.core.models import SearchResponse

logger = logging.getLogger(__name__)


async def search_books(
    client: ApiClient,
    query: str,
    *,
    limit: int = 10,
) -> SearchResponse:
    """Search the O'Reilly catalog by free-text query.

    Parameters
    ----------
    client:
        Authenticated API client.
    query:
        Free-text search query (title, author, topic, etc.).
    limit:
        Maximum number of results to return (default 10).

    Returns:
    -------
    SearchResponse
        Parsed search results.

    Raises:
    ------
    SearchError
        When the search API is unreachable or returns an error.

    """
    url = SEARCH_QUERY_TEMPLATE.format(query=quote_plus(query), limit=limit)
    try:
        data = await client.get_json(url)
    except ApiError as exc:
        raise SearchError(f"Search failed for query '{query}': {exc}") from exc

    return SearchResponse.model_validate(data)
