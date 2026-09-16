"""The address the app believes a request came from.

Rate limiting and audit records are only as good as this value, and behind a CDN
plus a platform router it can only come from ``X-Forwarded-For`` - a header that
the visitor writes the first entry of. These tests pin the counting rule.
"""

from __future__ import annotations

import pytest

from asme.utils.http import request_client_ip
from tests.conftest import make_app

SOCKET = {"REMOTE_ADDR": "10.0.0.9"}


def _ip(proxies, forwarded=None, remote_addr="10.0.0.9"):
    app = make_app(trusted_proxy_count=proxies)
    headers = {"X-Forwarded-For": forwarded} if forwarded is not None else {}
    with app.test_request_context("/api/v1/auth/login", headers=headers, environ_base={"REMOTE_ADDR": remote_addr}):
        return request_client_ip()


def test_no_trusted_proxies_uses_the_socket_address():
    # Nobody can forge the socket peer, so a header is ignored entirely.
    assert _ip(0, "203.0.113.7") == "10.0.0.9"
    assert _ip(0) == "10.0.0.9"


def test_two_proxies_take_the_second_entry_from_the_right():
    # browser -> CDN (appends the visitor) -> platform router (appends the CDN).
    assert _ip(2, "203.0.113.7, 198.51.100.4") == "203.0.113.7"


def test_entries_the_visitor_added_are_skipped():
    # A visitor who pre-seeds the header only pushes their own address rightwards:
    # counting from the right still lands on what the CDN actually saw.
    assert _ip(2, "1.2.3.4, 203.0.113.7, 198.51.100.4") == "203.0.113.7"


def test_a_chain_shorter_than_the_proxy_count_is_not_believed():
    # Fewer entries than configured means the request did not come through the
    # proxies we were told to expect - so the header is whatever the caller
    # typed, and the socket address is used instead.
    assert _ip(2, "1.2.3.4") == "10.0.0.9"
    assert _ip(2, "") == "10.0.0.9"
    assert _ip(1, "") == "10.0.0.9"


def test_entries_that_are_not_addresses_are_rejected():
    for forwarded in ("unknown, 198.51.100.4", "evil.example.org, 198.51.100.4", "<script>, 198.51.100.4"):
        assert _ip(2, forwarded) == "10.0.0.9", forwarded


def test_ports_and_brackets_are_stripped():
    assert _ip(2, "203.0.113.7:51820, 198.51.100.4") == "203.0.113.7"
    assert _ip(2, "[2001:db8::1]:443, 198.51.100.4") == "2001:db8::1"


def test_ipv6_is_kept():
    assert _ip(1, "2001:db8::1") == "2001:db8::1"


def test_missing_socket_address_never_returns_none():
    app = make_app(trusted_proxy_count=0)
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": ""}):
        assert request_client_ip() == "unknown"


@pytest.mark.parametrize("proxies", [0, 1, 2, 3])
def test_the_result_is_always_a_short_string(proxies):
    value = _ip(proxies, "203.0.113.7, 198.51.100.4, 192.0.2.1")
    assert isinstance(value, str) and 0 < len(value) <= 120
