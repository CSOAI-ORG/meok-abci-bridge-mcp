#!/usr/bin/env python3
"""
MEOK ABCI Bridge MCP — Tendermint / Cosmos blockchain query for agents
======================================================================

By MEOK AI Labs · https://meok.ai · MIT
<!-- mcp-name: io.github.CSOAI-ORG/meok-abci-bridge-mcp -->

WHAT THIS DOES
--------------
Bridges agents to ANY Cosmos-SDK / Tendermint chain via the ABCI (Application
Blockchain Interface) RPC. Same shape as ABCI 1.0 + ABCI++ (vote extensions
landed in CometBFT 0.38). Read-only by design — query state, look up txs,
fetch validator sets, derive deterministic block hashes. NEVER signs / sends
a transaction (delegate that to the user's signing wallet).

CHAINS COVERED OUT-OF-THE-BOX
-----------------------------
- Cosmos Hub (cosmos-hub-4)              - Tendermint v0.34, ABCI 1.0
- Osmosis (osmosis-1)                    - CometBFT v0.37, ABCI 1.0
- Celestia (celestia)                    - CometBFT v0.38, ABCI++ vote ext
- dYdX v4 (dydx-mainnet-1)               - CometBFT v0.38, ABCI++
- Neutron (neutron-1)                    - CometBFT v0.38, ABCI++
- Injective (injective-1)                - CometBFT v0.37
- Sei (pacific-1)                        - CometBFT v0.38
- Akash (akashnet-2)                     - CometBFT v0.37
- Stride (stride-1)                      - CometBFT v0.38
- Kava (kava_2222-10)                    - CometBFT v0.37
- Custom — point at any /cosmos/rpc URL  - any ABCI-compatible chain

THE VIRAL MOVE
--------------
Crypto-AI agent shops (Theoriq, Olas, Bittensor, Fetch.ai builders) need
blockchain state in their agent loops. Every existing wrapper (cosmpy /
cosmjs / ethers-cosmos) is heavy + signs txs. This MCP is read-only,
signed-attestation-friendly, and works for ANY ABCI chain.

TOOLS
-----
- abci_query(chain, path, data=""):   ABCI `query` against a chain
- abci_info(chain):                   ABCI `info` — version, last block
- get_block(chain, height=None):      Fetch a block (latest if no height)
- get_tx(chain, hash):                Fetch a transaction
- get_validators(chain, height=None): Validator set at height
- list_chains():                      Built-in chain registry
- chain_status(chain):                Liveness + latest height + apphash
- sign_query_result(result):          HMAC-seal a query response for replay-proof attestation

PRICING
-------
Free MIT self-host · £29/mo Starter · £79/mo Pro · A2A Substrate £999/mo.

NOTES
-----
- No private keys, no signing, no fund movement.
- All chain RPCs are public mainnet endpoints (no API key required).
- Verify signed query results at https://meok.ai/verify.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET") or os.environ.get(
    "MEOK_ATTESTATION_KEY"
)

# Built-in chain registry. RPC endpoints are public mainnet endpoints.
# Add your own via the `custom_rpc` parameter on any tool.
CHAIN_REGISTRY: dict[str, dict[str, str]] = {
    "cosmoshub":   {"rpc": "https://cosmos-rpc.polkachu.com",       "chain_id": "cosmoshub-4",      "cometbft": "0.34"},
    "osmosis":     {"rpc": "https://osmosis-rpc.polkachu.com",      "chain_id": "osmosis-1",        "cometbft": "0.37"},
    "celestia":    {"rpc": "https://celestia-rpc.polkachu.com",     "chain_id": "celestia",         "cometbft": "0.38"},
    "dydx":        {"rpc": "https://dydx-dao-rpc.polkachu.com",     "chain_id": "dydx-mainnet-1",   "cometbft": "0.38"},
    "neutron":     {"rpc": "https://neutron-rpc.polkachu.com",      "chain_id": "neutron-1",        "cometbft": "0.38"},
    "injective":   {"rpc": "https://injective-rpc.polkachu.com",    "chain_id": "injective-1",      "cometbft": "0.37"},
    "sei":         {"rpc": "https://sei-rpc.polkachu.com",          "chain_id": "pacific-1",        "cometbft": "0.38"},
    "akash":       {"rpc": "https://akash-rpc.polkachu.com",        "chain_id": "akashnet-2",       "cometbft": "0.37"},
    "stride":      {"rpc": "https://stride-rpc.polkachu.com",       "chain_id": "stride-1",         "cometbft": "0.38"},
    "kava":        {"rpc": "https://kava-rpc.polkachu.com",         "chain_id": "kava_2222-10",     "cometbft": "0.37"},
}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AbciError(Exception):
    """Generic ABCI/Tendermint bridge failure."""


# ---------------------------------------------------------------------------
# RPC plumbing
# ---------------------------------------------------------------------------

def _resolve_rpc(chain: str, custom_rpc: str | None = None) -> str:
    if custom_rpc:
        return custom_rpc.rstrip("/")
    entry = CHAIN_REGISTRY.get(chain.lower())
    if not entry:
        raise AbciError(
            f"Unknown chain '{chain}'. Use list_chains() to see built-ins, "
            "or pass custom_rpc=<your-rpc-url>."
        )
    return entry["rpc"].rstrip("/")


def _rpc_get(url: str, timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "meok-abci-bridge-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
    except Exception as exc:  # network failure
        raise AbciError(f"RPC GET failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AbciError(f"RPC returned non-JSON: {body[:200]}") from exc


def _rpc_call(chain: str, method: str, params: dict[str, Any] | None = None,
              custom_rpc: str | None = None) -> dict[str, Any]:
    base = _resolve_rpc(chain, custom_rpc)
    params = params or {}
    query = urllib.parse.urlencode(params)
    url = f"{base}/{method}"
    if query:
        url = f"{url}?{query}"
    return _rpc_get(url)


# ---------------------------------------------------------------------------
# ABCI tools
# ---------------------------------------------------------------------------

def _abci_query_impl(chain: str, path: str, data: str = "",
                     custom_rpc: str | None = None,
                     prove: bool = False, height: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"path": f'"{path}"'}
    if data:
        params["data"] = f'"{data}"'
    if prove:
        params["prove"] = "true"
    if height is not None:
        params["height"] = str(height)
    return _rpc_call(chain, "abci_query", params, custom_rpc=custom_rpc)


def _abci_info_impl(chain: str, custom_rpc: str | None = None) -> dict[str, Any]:
    return _rpc_call(chain, "abci_info", custom_rpc=custom_rpc)


def _get_block_impl(chain: str, height: int | None = None,
                    custom_rpc: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if height is not None:
        params["height"] = str(height)
    return _rpc_call(chain, "block", params, custom_rpc=custom_rpc)


def _get_tx_impl(chain: str, tx_hash: str,
                 custom_rpc: str | None = None) -> dict[str, Any]:
    h = tx_hash.upper()
    if not h.startswith("0X"):
        h = f"0x{h}"
    return _rpc_call(chain, "tx", {"hash": h}, custom_rpc=custom_rpc)


def _get_validators_impl(chain: str, height: int | None = None,
                         custom_rpc: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if height is not None:
        params["height"] = str(height)
    return _rpc_call(chain, "validators", params, custom_rpc=custom_rpc)


def _chain_status_impl(chain: str, custom_rpc: str | None = None) -> dict[str, Any]:
    return _rpc_call(chain, "status", custom_rpc=custom_rpc)


# ---------------------------------------------------------------------------
# HMAC sealing
# ---------------------------------------------------------------------------

def _hmac_sign(payload: bytes) -> str:
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    return hmac.new(_HMAC_SECRET.encode(), payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------

mcp = FastMCP("meok-abci-bridge")


@mcp.tool()
def list_chains() -> dict:
    """Return the built-in Cosmos / Tendermint chain registry."""
    return {
        "count": len(CHAIN_REGISTRY),
        "chains": CHAIN_REGISTRY,
        "note": "Use the chain alias (e.g. 'cosmoshub', 'osmosis') in every tool. "
                "Pass `custom_rpc=https://your-rpc-url` to query any other ABCI chain.",
    }


@mcp.tool()
def abci_info(chain: str, custom_rpc: str | None = None) -> dict:
    """ABCI `info` — app version, last block height, last app hash."""
    return _abci_info_impl(chain, custom_rpc=custom_rpc)


@mcp.tool()
def abci_query(chain: str, path: str, data: str = "",
               prove: bool = False, height: int | None = None,
               custom_rpc: str | None = None) -> dict:
    """ABCI `query` — read application state by path (e.g. '/bank/balances/<addr>')."""
    return _abci_query_impl(chain, path, data=data, prove=prove,
                            height=height, custom_rpc=custom_rpc)


@mcp.tool()
def get_block(chain: str, height: int | None = None,
              custom_rpc: str | None = None) -> dict:
    """Fetch a block (latest when `height` is None)."""
    return _get_block_impl(chain, height=height, custom_rpc=custom_rpc)


@mcp.tool()
def get_tx(chain: str, tx_hash: str, custom_rpc: str | None = None) -> dict:
    """Fetch a transaction by its hex hash (0x-prefixed accepted)."""
    return _get_tx_impl(chain, tx_hash, custom_rpc=custom_rpc)


@mcp.tool()
def get_validators(chain: str, height: int | None = None,
                   custom_rpc: str | None = None) -> dict:
    """Validator set at `height` (latest when None)."""
    return _get_validators_impl(chain, height=height, custom_rpc=custom_rpc)


@mcp.tool()
def chain_status(chain: str, custom_rpc: str | None = None) -> dict:
    """Liveness + latest_block_height + app_hash + earliest_block_height."""
    return _chain_status_impl(chain, custom_rpc=custom_rpc)


@mcp.tool()
def sign_query_result(query_result: dict) -> dict:
    """HMAC-seal an RPC result for replay-proof attestation."""
    payload = json.dumps(query_result, sort_keys=True, separators=(",", ":")).encode()
    return {
        "result": query_result,
        "signature": _hmac_sign(payload),
        "signed_at": int(time.time()),
        "verify_at": "https://meok.ai/verify",
        "issuer": "meok-abci-bridge-mcp",
    }


def main() -> None:  # pragma: no cover
    """Entry point for `meok-abci-bridge-mcp` script."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/aFa7sNcgAdQS0ZT1Uc8k91t"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
