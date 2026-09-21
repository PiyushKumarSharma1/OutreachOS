"""Tests for the REAL keyless providers (no network required)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from outreachos.providers.real import (
    _read_name, _dns_query_mx, _domain_of, _hn_html_to_text, _match_any,
    MxEmailFinder, SmtpSender, WebsiteResearch, RemoteOkSource, HNHiringSource,
)


def test_read_name_simple():
    data = b"\x00" * 12 + b"\x03foo\x03com\x00" + b"\x00\x00\x0f\x00\x01"
    name, nxt = _read_name(data, 12)
    assert name == "foo.com"
    assert nxt == 12 + len(b"\x03foo\x03com\x00")


def test_read_name_compression_pointer():
    # name at 12: "a.com", name at 19: "mail." + pointer back to 12
    data = b"\x00" * 12 + b"\x01a\x03com\x00" + b"\x04mail\xc0\x0c" + b"\xff" * 8
    name, nxt = _read_name(data, 19)
    assert name == "mail.a.com"
    assert nxt == 26


def test_domain_of():
    assert _domain_of("https://www.checklyhq.com/jobs") == "checklyhq.com"
    assert _domain_of("www.foo.io") == "foo.io"
    assert _domain_of("") == ""


def test_hn_html_to_text():
    assert "line1" in _hn_html_to_text("<p>line1</p><p>line2</p>")


def test_match_any():
    assert _match_any("Hiring SDR", ["sdr"])
    assert not _match_any("Engineer", ["sdr"])


def test_mx_finder_no_domain():
    f = MxEmailFinder()
    assert f.find_email("", "", "") == {}


def test_smtp_sender_draft_mode(monkeypatch, tmp_path):
    s = SmtpSender(drafts_dir=str(tmp_path))
    assert not s.live  # no creds + LIVE_SEND unset -> draft mode
    results = s.send_batch("cmp1", [{"to": "x@test.com", "subject": "hi", "body": "hello"}])
    assert results[0]["status"] == "draft_written"
    assert (tmp_path / "x_cmp1.eml").exists()


def test_remoteok_source_offline_returns_empty(monkeypatch):
    src = RemoteOkSource()
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr("outreachos.providers.real._get_json", boom)
    assert src.source_leads({}, 5) == []


def test_hn_source_offline_returns_empty(monkeypatch):
    src = HNHiringSource()
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr("outreachos.providers.real._get_json", boom)
    assert src.source_leads({}, 5) == []
