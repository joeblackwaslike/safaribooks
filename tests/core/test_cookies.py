"""Tests for safaribooks.core.cookies."""


import json

import pytest

from safaribooks.core.cookies import (
    from_file,
    normalize_cookies,
    parse_auto,
    parse_header,
    save,
    validate,
)
from safaribooks.core.exceptions import CookieError
from safaribooks.core.models import CookieSet

VALID_COOKIES = {
    "groot_sessionid": "abc123",
    "jwt": "eyJ0eXAi.payload.sig",
    "csrf_access_token": "csrf_token_value",
    "logged_in": "1",
}


class TestNormalizeCookies:
    def test_strips_whitespace(self):
        raw = {"  jwt  ": "  token_value  ", "key": "val"}
        result = normalize_cookies(raw)
        assert result == {"jwt": "token_value", "key": "val"}

    def test_removes_empty_keys(self):
        raw = {"": "value", "jwt": "tok"}
        result = normalize_cookies(raw)
        assert "" not in result
        assert result == {"jwt": "tok"}

    def test_removes_empty_values(self):
        raw = {"jwt": "", "key": "val"}
        result = normalize_cookies(raw)
        assert "jwt" not in result
        assert result == {"key": "val"}

    def test_removes_whitespace_only_entries(self):
        raw = {"  ": "   ", "jwt": "tok"}
        result = normalize_cookies(raw)
        assert result == {"jwt": "tok"}

    def test_passthrough_clean_cookies(self):
        result = normalize_cookies({"a": "1", "b": "2"})
        assert result == {"a": "1", "b": "2"}


class TestParseHeader:
    def test_basic_header(self):
        result = parse_header("jwt=tok123; csrf=abc")
        assert result == {"jwt": "tok123", "csrf": "abc"}

    def test_header_with_cookie_prefix(self):
        result = parse_header("Cookie: jwt=tok; csrf=abc")
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_header_with_case_insensitive_prefix(self):
        result = parse_header("cookie: jwt=tok; csrf=abc")
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_empty_string(self):
        result = parse_header("")
        assert result == {}

    def test_only_cookie_prefix(self):
        result = parse_header("Cookie:")
        assert result == {}

    def test_values_with_equals_signs(self):
        result = parse_header("jwt=a=b=c; key=val")
        assert result["jwt"] == "a=b=c"
        assert result["key"] == "val"

    def test_extra_whitespace(self):
        result = parse_header("  jwt = tok ;  csrf = abc  ")
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_trailing_semicolons(self):
        result = parse_header("jwt=tok;;csrf=abc;")
        assert result == {"jwt": "tok", "csrf": "abc"}


class TestParseAuto:
    def test_json_dict(self):
        text = json.dumps({"jwt": "tok", "csrf": "abc"})
        result = parse_auto(text)
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_json_array_extension_export(self):
        export = [
            {"name": "jwt", "value": "tok", "domain": ".oreilly.com"},
            {"name": "csrf", "value": "abc", "domain": ".oreilly.com"},
        ]
        result = parse_auto(json.dumps(export))
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_json_array_filters_non_oreilly_domains(self):
        export = [
            {"name": "jwt", "value": "tok", "domain": ".oreilly.com"},
            {"name": "other", "value": "val", "domain": ".google.com"},
        ]
        result = parse_auto(json.dumps(export))
        assert "jwt" in result
        assert "other" not in result

    def test_json_array_includes_entries_without_domain(self):
        export = [
            {"name": "jwt", "value": "tok"},
        ]
        result = parse_auto(json.dumps(export))
        assert result == {"jwt": "tok"}

    def test_raw_header_fallback(self):
        result = parse_auto("jwt=tok; csrf=abc")
        assert result == {"jwt": "tok", "csrf": "abc"}

    def test_double_encoded_json(self):
        inner = json.dumps({"jwt": "tok"})
        outer = json.dumps(inner)
        result = parse_auto(outer)
        assert result == {"jwt": "tok"}

    def test_empty_input(self):
        result = parse_auto("")
        assert result == {}


class TestValidate:
    def test_valid_cookies_return_cookie_set(self):
        result = validate(VALID_COOKIES)
        assert isinstance(result, CookieSet)
        assert result.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_missing_required_raises_cookie_error(self):
        with pytest.raises(CookieError, match="Missing required cookies"):
            validate({"jwt": "tok"})

    def test_empty_dict_raises_cookie_error(self):
        with pytest.raises(CookieError, match="No cookies provided"):
            validate({})


class TestFromFile:
    def test_reads_json_dict_file(self, tmp_path):
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(VALID_COOKIES))
        result = from_file(cookie_file)
        assert isinstance(result, CookieSet)
        assert result.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_reads_extension_export_file(self, tmp_path):
        export = [
            {"name": k, "value": v, "domain": ".oreilly.com"} for k, v in VALID_COOKIES.items()
        ]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(export))
        result = from_file(cookie_file)
        assert isinstance(result, CookieSet)

    def test_missing_file_raises_cookie_error(self, tmp_path):
        with pytest.raises(CookieError, match="Cookie file not found"):
            from_file(tmp_path / "nonexistent.json")

    def test_unparseable_file_raises_cookie_error(self, tmp_path):
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("not valid anything")
        with pytest.raises(CookieError, match="Could not parse cookie file"):
            from_file(cookie_file)


class TestSave:
    def test_writes_json_with_correct_content(self, tmp_path):
        cs = CookieSet(cookies=VALID_COOKIES)
        output = tmp_path / "out_cookies.json"
        save(cs, output)
        assert output.is_file()
        loaded = json.loads(output.read_text())
        assert loaded == VALID_COOKIES

    def test_creates_parent_directories(self, tmp_path):
        cs = CookieSet(cookies=VALID_COOKIES)
        output = tmp_path / "deep" / "nested" / "cookies.json"
        save(cs, output)
        assert output.is_file()

    def test_output_ends_with_newline(self, tmp_path):
        cs = CookieSet(cookies=VALID_COOKIES)
        output = tmp_path / "cookies.json"
        save(cs, output)
        text = output.read_text()
        assert text.endswith("\n")
