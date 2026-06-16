"""Tests for safaribooks.core.cookies."""


import json
import sys
import types

import pytest

import safaribooks.core.cookies as cookies_mod
from safaribooks.core.cookies import (
    from_browser,
    from_file,
    from_header,
    from_paste,
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

    def test_chmod_failure_is_swallowed(self, tmp_path, monkeypatch):
        cs = CookieSet(cookies=VALID_COOKIES)
        output = tmp_path / "cookies.json"

        original_chmod = cookies_mod.Path.chmod

        def boom(self, mode):
            raise OSError("no chmod here")

        monkeypatch.setattr(cookies_mod.Path, "chmod", boom)
        try:
            # Should not raise despite chmod failure.
            save(cs, output)
        finally:
            monkeypatch.setattr(cookies_mod.Path, "chmod", original_chmod)
        assert output.is_file()


class TestParseAutoArrayBranch:
    def test_array_first_item_without_name_falls_through_to_header(self):
        # A JSON array whose first element lacks "name" does not match the
        # extension-export branch (68->80); _parse_auto falls back to header
        # parsing, which finds no "=" pairs and returns {}.
        result = parse_auto(json.dumps([{"value": "v"}]))
        assert result == {}

    def test_empty_array_falls_through(self):
        result = parse_auto(json.dumps([]))
        assert result == {}


class TestValidateWarnings:
    def test_few_cookies_logs_warning(self, caplog):
        with caplog.at_level("WARNING"), pytest.raises(CookieError):
            validate({"jwt": "tok"})
        assert any("may be incomplete" in r.message for r in caplog.records)

    def test_empty_value_logs_warning(self, caplog):
        cookies = dict(VALID_COOKIES)
        cookies["extra_empty"] = ""
        with caplog.at_level("WARNING"):
            result = validate(cookies)
        assert isinstance(result, CookieSet)
        assert any("Empty values for cookies" in r.message for r in caplog.records)

    def test_non_missing_value_error_passes_through_message(self, monkeypatch):
        # When CookieSet raises a ValueError that is NOT about missing cookies
        # (all required cookies present, so `missing` is empty), the original
        # exception message should be surfaced (else-branch of line 219).
        def fake_cookie_set(*args, **kwargs):
            raise ValueError("some other validation problem")

        monkeypatch.setattr(cookies_mod, "CookieSet", fake_cookie_set)
        with pytest.raises(CookieError, match="some other validation problem"):
            validate(VALID_COOKIES)


class TestFromHeader:
    def test_valid_header_returns_cookie_set(self):
        header = "; ".join(f"{k}={v}" for k, v in VALID_COOKIES.items())
        result = from_header(header)
        assert isinstance(result, CookieSet)
        assert result.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_empty_header_raises(self):
        with pytest.raises(CookieError, match="Could not parse cookie header"):
            from_header("Cookie:")

    def test_header_missing_required_raises(self):
        with pytest.raises(CookieError, match="Missing required cookies"):
            from_header("jwt=tok")


class _FakeCookie:
    def __init__(self, name, value):
        self.name = name
        self.value = value


def _install_fake_bc3(monkeypatch, *, jar=None, raise_on_call=None):
    """Install a fake browser_cookie3 module in sys.modules."""
    module = types.ModuleType("browser_cookie3")

    def make(loader_jar, exc):
        def loader(domain_name=None):
            if exc is not None:
                raise exc
            return loader_jar

        return loader

    jar = jar or []
    for name in ("chrome", "firefox", "edge", "chromium"):
        setattr(module, name, make(jar, raise_on_call))
    monkeypatch.setitem(sys.modules, "browser_cookie3", module)
    return module


class TestFromBrowser:
    def test_import_error_raises_cookie_error(self, monkeypatch):
        # Ensure the import inside the function fails.
        monkeypatch.setitem(sys.modules, "browser_cookie3", None)
        with pytest.raises(CookieError, match="browser_cookie3 is not installed"):
            from_browser("chrome")

    def test_unsupported_browser_raises(self, monkeypatch):
        _install_fake_bc3(monkeypatch)
        with pytest.raises(CookieError, match="Unsupported browser"):
            from_browser("safari")

    def test_extraction_failure_raises(self, monkeypatch):
        _install_fake_bc3(monkeypatch, raise_on_call=RuntimeError("locked db"))
        with pytest.raises(CookieError, match="Failed to extract cookies"):
            from_browser("chrome")

    def test_successful_extraction_returns_cookie_set(self, monkeypatch):
        jar = [_FakeCookie(k, v) for k, v in VALID_COOKIES.items()]
        _install_fake_bc3(monkeypatch, jar=jar)
        result = from_browser("firefox")
        assert isinstance(result, CookieSet)
        assert result.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_extraction_missing_required_raises(self, monkeypatch):
        jar = [_FakeCookie("jwt", "tok")]
        _install_fake_bc3(monkeypatch, jar=jar)
        with pytest.raises(CookieError, match="Missing required cookies"):
            from_browser("edge")


class TestFromPaste:
    def _patch_prompt(self, monkeypatch, lines):
        it = iter(lines)

        def fake_ask(*args, **kwargs):
            try:
                return next(it)
            except StopIteration:
                return ""

        monkeypatch.setattr(cookies_mod.Prompt, "ask", staticmethod(fake_ask))

    def test_paste_header_lines(self, monkeypatch):
        header = "; ".join(f"{k}={v}" for k, v in VALID_COOKIES.items())
        self._patch_prompt(monkeypatch, [header, ""])
        result = from_paste()
        assert isinstance(result, CookieSet)
        assert result.cookies["logged_in"] == "1"

    def test_paste_json(self, monkeypatch):
        self._patch_prompt(monkeypatch, [json.dumps(VALID_COOKIES), ""])
        result = from_paste()
        assert isinstance(result, CookieSet)

    def test_paste_empty_input_raises(self, monkeypatch):
        self._patch_prompt(monkeypatch, ["", ""])
        with pytest.raises(CookieError, match="Empty input"):
            from_paste()

    def test_paste_eof_then_empty_raises(self, monkeypatch):
        def fake_ask(*args, **kwargs):
            raise EOFError

        monkeypatch.setattr(cookies_mod.Prompt, "ask", staticmethod(fake_ask))
        with pytest.raises(CookieError, match="Empty input"):
            from_paste()

    def test_paste_unparseable_raises(self, monkeypatch):
        self._patch_prompt(monkeypatch, ["this has no equals or json", ""])
        with pytest.raises(CookieError, match="Could not parse input"):
            from_paste()

    def test_paste_eof_after_valid_line(self, monkeypatch):
        header = "; ".join(f"{k}={v}" for k, v in VALID_COOKIES.items())
        calls = iter([header])

        def fake_ask(*args, **kwargs):
            try:
                return next(calls)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr(cookies_mod.Prompt, "ask", staticmethod(fake_ask))
        result = from_paste()
        assert isinstance(result, CookieSet)
