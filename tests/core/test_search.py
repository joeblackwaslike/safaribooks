"""Tests for safaribooks.core.search."""


from unittest.mock import AsyncMock, MagicMock

import pytest

from safaribooks.core.exceptions import ApiError, SearchError
from safaribooks.core.models import SearchResponse
from safaribooks.core.search import search_books


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.get_json = AsyncMock()
    return client


class TestSearchBooks:
    @pytest.mark.asyncio
    async def test_returns_parsed_results(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "results": [
                {
                    "title": "Python Crash Course",
                    "isbn": "9781718502703",
                    "archive_id": "9781718502703",
                    "authors": ["Eric Matthes"],
                    "publishers": "No Starch Press",
                },
                {
                    "title": "Automate the Boring Stuff",
                    "isbn": "9781593279929",
                    "authors": ["Al Sweigart"],
                },
            ],
            "count": 2,
            "total": 42,
        }

        response = await search_books(mock_client, "python crash course")

        assert isinstance(response, SearchResponse)
        assert len(response.results) == 2
        assert response.results[0].title == "Python Crash Course"
        assert response.results[0].book_id == "9781718502703"
        assert response.results[1].authors == ["Al Sweigart"]
        assert response.count == 2
        assert response.total == 42

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"results": [], "count": 0, "total": 0}

        response = await search_books(mock_client, "nonexistent book xyz")

        assert response.results == []
        assert response.count == 0

    @pytest.mark.asyncio
    async def test_api_error_raises_search_error(self, mock_client: MagicMock):
        mock_client.get_json.side_effect = ApiError("Server error")

        with pytest.raises(SearchError, match="Search failed"):
            await search_books(mock_client, "python")

    @pytest.mark.asyncio
    async def test_url_encodes_query(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"results": [], "count": 0, "total": 0}

        await search_books(mock_client, "Python Crash Course")

        url = mock_client.get_json.call_args[0][0]
        assert "Python+Crash+Course" in url

    @pytest.mark.asyncio
    async def test_limit_parameter(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"results": [], "count": 0, "total": 0}

        await search_books(mock_client, "python", limit=5)

        url = mock_client.get_json.call_args[0][0]
        assert "limit=5" in url

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"results": [], "count": 0, "total": 0}

        await search_books(mock_client, "python")

        url = mock_client.get_json.call_args[0][0]
        assert "limit=10" in url
