"""Unit tests for meok-abci-bridge-mcp."""
from __future__ import annotations

import os
import sys
import json
import pathlib
from unittest.mock import patch, MagicMock

os.environ.setdefault("MEOK_HMAC_SECRET", "test-only-secret")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from server import (  # noqa: E402
    CHAIN_REGISTRY,
    AbciError,
    _resolve_rpc,
    list_chains,
    sign_query_result,
    _hmac_sign,
)


# ---------- registry ----------

def test_registry_has_10_chains():
    assert len(CHAIN_REGISTRY) == 10


def test_registry_known_chains_present():
    for chain in ("cosmoshub", "osmosis", "celestia", "dydx", "neutron",
                  "injective", "sei", "akash", "stride", "kava"):
        assert chain in CHAIN_REGISTRY
        entry = CHAIN_REGISTRY[chain]
        assert entry["rpc"].startswith("https://")
        assert entry["chain_id"]
        assert entry["cometbft"]


def test_list_chains_tool_output():
    out = list_chains()
    assert out["count"] == 10
    assert "cosmoshub" in out["chains"]
    assert "note" in out


# ---------- RPC resolution ----------

def test_resolve_rpc_known_chain():
    rpc = _resolve_rpc("cosmoshub")
    assert rpc.startswith("https://")
    # No trailing slash
    assert not rpc.endswith("/")


def test_resolve_rpc_case_insensitive():
    a = _resolve_rpc("Osmosis")
    b = _resolve_rpc("OSMOSIS")
    c = _resolve_rpc("osmosis")
    assert a == b == c


def test_resolve_rpc_unknown_raises():
    try:
        _resolve_rpc("not-a-real-chain")
        assert False, "Expected AbciError"
    except AbciError as e:
        assert "Unknown chain" in str(e)
        assert "custom_rpc" in str(e)


def test_resolve_rpc_custom_takes_precedence():
    rpc = _resolve_rpc("cosmoshub", custom_rpc="https://my-private-rpc/")
    assert rpc == "https://my-private-rpc"


# ---------- HMAC sealing ----------

def test_hmac_sign_with_key():
    sig = _hmac_sign(b"hello")
    assert len(sig) == 64  # sha256 hex
    assert sig != "unsigned-no-key-configured"


def test_hmac_sign_deterministic():
    assert _hmac_sign(b"x") == _hmac_sign(b"x")


def test_hmac_sign_no_key_returns_marker():
    # Temporarily unset the key
    import server
    saved = server._HMAC_SECRET
    server._HMAC_SECRET = None
    try:
        assert server._hmac_sign(b"x") == "unsigned-no-key-configured"
    finally:
        server._HMAC_SECRET = saved


def test_sign_query_result_returns_signature():
    raw = {"jsonrpc": "2.0", "result": {"latest_block_height": "12345"}}
    sealed = sign_query_result(raw)
    assert sealed["signature"] != "unsigned-no-key-configured"
    assert sealed["result"] == raw
    assert sealed["issuer"] == "meok-abci-bridge-mcp"
    assert sealed["verify_at"] == "https://meok.ai/verify"


# ---------- mocked RPC calls (no network) ----------

def test_chain_status_calls_correct_url(monkeypatch):
    """Verify chain_status hits /status on the right RPC base."""
    captured = {}

    def fake_rpc_get(url: str, timeout: float = 8.0):
        captured["url"] = url
        return {"jsonrpc": "2.0", "result": {"sync_info": {"latest_block_height": "1"}}}

    import server
    monkeypatch.setattr(server, "_rpc_get", fake_rpc_get)
    out = server.chain_status("cosmoshub")
    assert captured["url"].endswith("/status")
    assert "polkachu" in captured["url"]
    assert out["result"]["sync_info"]["latest_block_height"] == "1"


def test_abci_query_sends_quoted_path(monkeypatch):
    captured = {}

    def fake_rpc_get(url: str, timeout: float = 8.0):
        captured["url"] = url
        return {"jsonrpc": "2.0", "result": {"response": {"value": ""}}}

    import server
    monkeypatch.setattr(server, "_rpc_get", fake_rpc_get)
    server.abci_query("celestia", "/cosmos.bank.v1beta1.Query/AllBalances")
    assert "abci_query" in captured["url"]
    assert "path=" in captured["url"]
    # URL-encoded form of `"/cosmos.bank..."`
    assert "%22" in captured["url"]


def test_get_tx_normalises_hash(monkeypatch):
    captured = {}

    def fake_rpc_get(url: str, timeout: float = 8.0):
        captured["url"] = url
        return {"jsonrpc": "2.0", "result": {"hash": "ABC"}}

    import server
    monkeypatch.setattr(server, "_rpc_get", fake_rpc_get)

    # Lowercase hex without 0x prefix
    server.get_tx("kava", "abcdef1234567890")
    assert "hash=" in captured["url"]
    # Should have prepended 0x and uppercased the hex digits
    assert "0xABCDEF1234567890" in captured["url"]
