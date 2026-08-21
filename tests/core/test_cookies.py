"""Tests for safaribooks.core.cookies."""

import json
import sys
import types

import pytest

from safaribooks.core import cookies as cookies_mod
from safaribooks.core.exceptions import CookieError
from safaribooks.core.models import CookieSet

VALID_COOKIES = types.MappingProxyType(
    {
        "groot_sessionid": "abc123",
        "jwt": "eyJ0eXAi.payload.sig",
        "csrf_access_token": "csrf_token_value",
        "logged_in": "1",
    },
)

_JWT_CSRF = types.MappingProxyType({"jwt": "tok", "csrf": "abc"})
_OREILLY_DOMAIN = ".oreilly.com"


def _valid_cookies() -> dict[str, str]:
    """Return a mutable copy of the canonical valid cookie mapping."""
    return dict(VALID_COOKIES)


def _assert_cookie_set(candidate: object) -> CookieSet:
    """Assert *candidate* is a CookieSet and return it for further checks."""
    assert isinstance(candidate, CookieSet)
    return candidate


def _header_from(cookies: types.MappingProxyType) -> str:
    """Build a Cookie header string from a name/value mapping."""
    return "; ".join(f"{name}={cookie_value}" for name, cookie_value in cookies.items())


def _fake_cookie(name: str, cookie_value: str) -> types.SimpleNamespace:
    """Build a stand-in browser cookie exposing .name and .value."""
    return types.SimpleNamespace(name=name, value=cookie_value)


class _FakeLoader:
    """Callable mimicking a browser_cookie3 loader function."""

    def __init__(self, jar, exc):
        self._jar = jar
        self._exc = exc

    def __call__(self, domain_name=None):
        if self._exc is not None:
            raise self._exc
        return self._jar


class _ScriptedPrompt:
    """Callable returning scripted lines in place of Prompt.ask."""

    def __init__(self, lines, *, then_eof=False, always_eof=False):
        self._lines = iter(lines)
        self._then_eof = then_eof
        self._always_eof = always_eof

    def __call__(self, *args, **kwargs):
        if self._always_eof:
            raise EOFError
        try:
            return next(self._lines)
        except StopIteration:
            if self._then_eof:
                raise EOFError from None
            return ""


def _raise_other_value_error(*args, **kwargs):
    """Stand-in CookieSet that raises an unrelated ValueError."""
    raise ValueError("some other validation problem")


def _raise_oserror_chmod(self, mode):
    """Stand-in Path.chmod that fails."""
    raise OSError("no chmod here")


def _install_fake_bc3(monkeypatch, *, jar=None, raise_on_call=None):
    """Install a fake browser_cookie3 module in sys.modules."""
    module = types.ModuleType("browser_cookie3")
    jar = jar or []
    for name in ("chrome", "firefox", "edge", "chromium"):
        setattr(module, name, _FakeLoader(jar, raise_on_call))
    monkeypatch.setitem(sys.modules, "browser_cookie3", module)
    return module


def _patch_prompt(monkeypatch, scripted):
    """Replace cookies_mod.Prompt.ask with a scripted callable."""
    monkeypatch.setattr(cookies_mod.Prompt, "ask", scripted)


class TestNormalizeCookies:
    def test_strips_whitespace(self):
        raw = {"  jwt  ": "  token_value  ", "key": "val"}
        outcome = cookies_mod.normalize_cookies(raw)
        assert outcome == {"jwt": "token_value", "key": "val"}

    def test_removes_empty_keys(self):
        raw = {"": "value", "jwt": "tok"}
        outcome = cookies_mod.normalize_cookies(raw)
        assert "" not in outcome
        assert outcome == {"jwt": "tok"}

    def test_removes_empty_values(self):
        raw = {"jwt": "", "key": "val"}
        outcome = cookies_mod.normalize_cookies(raw)
        assert "jwt" not in outcome
        assert outcome == {"key": "val"}

    def test_removes_whitespace_only_entries(self):
        raw = {"  ": "   ", "jwt": "tok"}
        outcome = cookies_mod.normalize_cookies(raw)
        assert outcome == {"jwt": "tok"}

    def test_passthrough_clean_cookies(self):
        outcome = cookies_mod.normalize_cookies({"a": "1", "b": "2"})
        assert outcome == {"a": "1", "b": "2"}


class TestParseHeader:
    def test_basic_header(self):
        outcome = cookies_mod.parse_header("jwt=tok123; csrf=abc")
        assert outcome == {"jwt": "tok123", "csrf": "abc"}

    def test_header_with_cookie_prefix(self):
        outcome = cookies_mod.parse_header("Cookie: jwt=tok; csrf=abc")
        assert outcome == _JWT_CSRF

    def test_header_with_case_insensitive_prefix(self):
        outcome = cookies_mod.parse_header("cookie: jwt=tok; csrf=abc")
        assert outcome == _JWT_CSRF

    def test_empty_string(self):
        outcome = cookies_mod.parse_header("")
        assert outcome == {}

    def test_only_cookie_prefix(self):
        outcome = cookies_mod.parse_header("Cookie:")
        assert outcome == {}


class TestParseHeaderEdgeCases:
    def test_values_with_equals_signs(self):
        outcome = cookies_mod.parse_header("jwt=a=b=c; key=val")
        assert outcome["jwt"] == "a=b=c"
        assert outcome["key"] == "val"

    def test_extra_whitespace(self):
        outcome = cookies_mod.parse_header("  jwt = tok ;  csrf = abc  ")
        assert outcome == _JWT_CSRF

    def test_trailing_semicolons(self):
        outcome = cookies_mod.parse_header("jwt=tok;;csrf=abc;")
        assert outcome == _JWT_CSRF


class TestParseAuto:
    def test_json_dict(self):
        text = json.dumps({"jwt": "tok", "csrf": "abc"})
        outcome = cookies_mod.parse_auto(text)
        assert outcome == _JWT_CSRF

    def test_json_array_extension_export(self):
        export = [
            {"name": "jwt", "value": "tok", "domain": _OREILLY_DOMAIN},
            {"name": "csrf", "value": "abc", "domain": _OREILLY_DOMAIN},
        ]
        outcome = cookies_mod.parse_auto(json.dumps(export))
        assert outcome == _JWT_CSRF

    def test_json_array_filters_non_oreilly_domains(self):
        export = [
            {"name": "jwt", "value": "tok", "domain": _OREILLY_DOMAIN},
            {"name": "other", "value": "val", "domain": ".google.com"},
        ]
        outcome = cookies_mod.parse_auto(json.dumps(export))
        assert "jwt" in outcome
        assert "other" not in outcome

    def test_json_array_entries_without_domain(self):
        export = [
            {"name": "jwt", "value": "tok"},
        ]
        outcome = cookies_mod.parse_auto(json.dumps(export))
        assert outcome == {"jwt": "tok"}

    def test_raw_header_fallback(self):
        outcome = cookies_mod.parse_auto("jwt=tok; csrf=abc")
        assert outcome == _JWT_CSRF

    def test_double_encoded_json(self):
        inner = json.dumps({"jwt": "tok"})
        outer = json.dumps(inner)
        outcome = cookies_mod.parse_auto(outer)
        assert outcome == {"jwt": "tok"}

    def test_empty_input(self):
        outcome = cookies_mod.parse_auto("")
        assert outcome == {}


class TestValidate:
    def test_valid_cookies_return_cookie_set(self):
        outcome = _assert_cookie_set(cookies_mod.validate(_valid_cookies()))
        assert outcome.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_missing_required_raises_cookie_error(self):
        with pytest.raises(CookieError, match="Missing required cookies"):
            cookies_mod.validate({"jwt": "tok"})

    def test_empty_dict_raises_cookie_error(self):
        with pytest.raises(CookieError, match="No cookies provided"):
            cookies_mod.validate({})


class TestFromFile:
    def test_reads_json_dict_file(self, tmp_path):
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(_valid_cookies()))
        outcome = _assert_cookie_set(cookies_mod.from_file(cookie_file))
        assert outcome.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_reads_extension_export_file(self, tmp_path):
        export = [
            {"name": name, "value": cookie_value, "domain": _OREILLY_DOMAIN}
            for name, cookie_value in VALID_COOKIES.items()
        ]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(export))
        _assert_cookie_set(cookies_mod.from_file(cookie_file))

    def test_missing_file_raises_cookie_error(self, tmp_path):
        with pytest.raises(CookieError, match="Cookie file not found"):
            cookies_mod.from_file(tmp_path / "nonexistent.json")

    def test_unparseable_file_raises_cookie_error(self, tmp_path):
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("not valid anything")
        with pytest.raises(CookieError, match="Could not parse cookie file"):
            cookies_mod.from_file(cookie_file)


class TestSave:
    def test_writes_json_with_correct_content(self, tmp_path):
        cookie_set = CookieSet(cookies=_valid_cookies())
        output = tmp_path / "out_cookies.json"
        cookies_mod.save(cookie_set, output)
        assert output.is_file()
        loaded = json.loads(output.read_text())
        assert loaded == VALID_COOKIES

    def test_creates_parent_directories(self, tmp_path):
        cookie_set = CookieSet(cookies=_valid_cookies())
        output = tmp_path / "deep" / "nested" / "cookies.json"
        cookies_mod.save(cookie_set, output)
        assert output.is_file()

    def test_output_ends_with_newline(self, tmp_path):
        cookie_set = CookieSet(cookies=_valid_cookies())
        output = tmp_path / "cookies.json"
        cookies_mod.save(cookie_set, output)
        text = output.read_text()
        assert text.endswith("\n")

    def test_chmod_failure_is_swallowed(self, tmp_path, monkeypatch):
        cookie_set = CookieSet(cookies=_valid_cookies())
        output = tmp_path / "cookies.json"
        monkeypatch.setattr(cookies_mod.Path, "chmod", _raise_oserror_chmod)
        # Should not raise despite chmod failure.
        cookies_mod.save(cookie_set, output)
        assert output.is_file()


class TestParseAutoArrayBranch:
    def test_array_first_item_without_name(self):
        # A JSON array whose first element lacks "name" does not match the
        # extension-export branch (68->80); _parse_auto falls back to header
        # parsing, which finds no "=" pairs and returns {}.
        outcome = cookies_mod.parse_auto(json.dumps([{"value": "v"}]))
        assert outcome == {}

    def test_empty_array_falls_through(self):
        outcome = cookies_mod.parse_auto(json.dumps([]))
        assert outcome == {}


class TestValidateWarnings:
    def test_few_cookies_logs_warning(self, caplog):
        with caplog.at_level("WARNING"), pytest.raises(CookieError):
            cookies_mod.validate({"jwt": "tok"})
        assert any("may be incomplete" in record.message for record in caplog.records)

    def test_empty_value_logs_warning(self, caplog):
        cookies = _valid_cookies()
        cookies["extra_empty"] = ""
        with caplog.at_level("WARNING"):
            outcome = _assert_cookie_set(cookies_mod.validate(cookies))
        assert outcome is not None
        assert any("Empty values for cookies" in record.message for record in caplog.records)

    def test_non_missing_value_error_message(self, monkeypatch):
        # When CookieSet raises a ValueError that is NOT about missing cookies
        # (all required cookies present, so `missing` is empty), the original
        # exception message should be surfaced (else-branch of line 219).
        monkeypatch.setattr(cookies_mod, "CookieSet", _raise_other_value_error)
        with pytest.raises(CookieError, match="some other validation problem"):
            cookies_mod.validate(_valid_cookies())


class TestFromHeader:
    def test_valid_header_returns_cookie_set(self):
        outcome = _assert_cookie_set(
            cookies_mod.from_header(_header_from(VALID_COOKIES)),
        )
        assert outcome.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_empty_header_raises(self):
        with pytest.raises(CookieError, match="Could not parse cookie header"):
            cookies_mod.from_header("Cookie:")

    def test_header_missing_required_raises(self):
        with pytest.raises(CookieError, match="Missing required cookies"):
            cookies_mod.from_header("jwt=tok")


class TestFromBrowser:
    def test_import_error_raises_cookie_error(self, monkeypatch):
        # Ensure the import inside the function fails.
        monkeypatch.setitem(sys.modules, "browser_cookie3", None)
        with pytest.raises(CookieError, match="browser_cookie3 is not installed"):
            cookies_mod.from_browser("chrome")

    def test_unsupported_browser_raises(self, monkeypatch):
        _install_fake_bc3(monkeypatch)
        with pytest.raises(CookieError, match="Unsupported browser"):
            cookies_mod.from_browser("safari")

    def test_extraction_failure_raises(self, monkeypatch):
        _install_fake_bc3(monkeypatch, raise_on_call=RuntimeError("locked db"))
        with pytest.raises(CookieError, match="Failed to extract cookies"):
            cookies_mod.from_browser("chrome")

    def test_successful_extraction_returns_cookie_set(self, monkeypatch):
        jar = [_fake_cookie(name, cookie_value) for name, cookie_value in VALID_COOKIES.items()]
        _install_fake_bc3(monkeypatch, jar=jar)
        outcome = _assert_cookie_set(cookies_mod.from_browser("firefox"))
        assert outcome.cookies["jwt"] == VALID_COOKIES["jwt"]

    def test_extraction_missing_required_raises(self, monkeypatch):
        jar = [_fake_cookie("jwt", "tok")]
        _install_fake_bc3(monkeypatch, jar=jar)
        with pytest.raises(CookieError, match="Missing required cookies"):
            cookies_mod.from_browser("edge")


class TestFromPaste:
    def test_paste_header_lines(self, monkeypatch):
        header = _header_from(VALID_COOKIES)
        _patch_prompt(monkeypatch, _ScriptedPrompt([header, ""]))
        outcome = _assert_cookie_set(cookies_mod.from_paste())
        assert outcome.cookies["logged_in"] == "1"

    def test_paste_json(self, monkeypatch):
        _patch_prompt(
            monkeypatch,
            _ScriptedPrompt([json.dumps(_valid_cookies()), ""]),
        )
        _assert_cookie_set(cookies_mod.from_paste())

    def test_paste_empty_input_raises(self, monkeypatch):
        _patch_prompt(monkeypatch, _ScriptedPrompt(["", ""]))
        with pytest.raises(CookieError, match="Empty input"):
            cookies_mod.from_paste()

    def test_paste_eof_then_empty_raises(self, monkeypatch):
        _patch_prompt(monkeypatch, _ScriptedPrompt([], always_eof=True))
        with pytest.raises(CookieError, match="Empty input"):
            cookies_mod.from_paste()

    def test_paste_unparseable_raises(self, monkeypatch):
        _patch_prompt(
            monkeypatch,
            _ScriptedPrompt(["this has no equals or json", ""]),
        )
        with pytest.raises(CookieError, match="Could not parse input"):
            cookies_mod.from_paste()

    def test_paste_eof_after_valid_line(self, monkeypatch):
        header = _header_from(VALID_COOKIES)
        _patch_prompt(monkeypatch, _ScriptedPrompt([header], then_eof=True))
        _assert_cookie_set(cookies_mod.from_paste())
