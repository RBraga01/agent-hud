"""Tests for the loopback check that gates binding off this machine."""

import pytest

from stub_server.net import LOOPBACK_HOST, is_loopback


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.53", "::1", "localhost", "LocalHost", "", "  "],
)
def test_these_keep_the_gateway_on_this_machine(host):
    assert is_loopback(host) is True


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "192.168.1.10", "10.0.0.1", "::", "example.com",
     "gateway.local", "203.0.113.7"],
)
def test_these_would_expose_it(host):
    assert is_loopback(host) is False


def test_the_default_bind_is_loopback():
    assert is_loopback(LOOPBACK_HOST) is True
