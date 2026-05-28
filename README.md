# MEOK ABCI Bridge MCP

> **Read-only Tendermint / Cosmos blockchain query for agents.** Built-in registry of 10 mainnets, ABCI 1.0 + ABCI++ vote extensions, HMAC-signed responses, never holds a private key.

> 🧱 **Part of the MEOK A2A Substrate (£999/mo)** — pairs with `meok-libp2p-agent-mesh-mcp` (mesh discovery), `meok-aaif-agent-card-mcp` (identity) and `meok-ap2-mandate-mcp` (payments).

## Why ABCI for agents

Crypto-AI agents (Theoriq, Olas, Bittensor, Fetch.ai builders, on-chain DAOs) need blockchain state in their loop. Existing wrappers (cosmpy / cosmjs / ethers-cosmos) are heavy, require signing keys, and lock you into one chain. This MCP:

- **Read-only.** No signing, no fund movement. Safe by construction.
- **Multi-chain.** 10 built-in mainnets, custom RPC for the rest.
- **Standards-clean.** ABCI 1.0 + ABCI++ (CometBFT 0.38 vote extensions).
- **Attestation-friendly.** Every result can be HMAC-sealed and verified at <https://meok.ai/verify>.

## Built-in chain registry

| Alias | Chain ID | CometBFT |
|---|---|---|
| `cosmoshub` | cosmoshub-4 | 0.34 |
| `osmosis` | osmosis-1 | 0.37 |
| `celestia` | celestia | 0.38 |
| `dydx` | dydx-mainnet-1 | 0.38 |
| `neutron` | neutron-1 | 0.38 |
| `injective` | injective-1 | 0.37 |
| `sei` | pacific-1 | 0.38 |
| `akash` | akashnet-2 | 0.37 |
| `stride` | stride-1 | 0.38 |
| `kava` | kava_2222-10 | 0.37 |

Plus `custom_rpc="https://..."` for any other ABCI-compatible chain.

## Quick start

```bash
pip install meok-abci-bridge-mcp
# or
uvx meok-abci-bridge-mcp
```

```python
from server import abci_info, chain_status, get_block, abci_query

# How tall is Celestia right now?
print(chain_status("celestia")["result"]["sync_info"]["latest_block_height"])

# Get the latest block on Cosmos Hub
print(get_block("cosmoshub"))

# Query bank balances on Osmosis
print(abci_query("osmosis", "/cosmos.bank.v1beta1.Query/AllBalances",
                 data="<base64-encoded-request>"))
```

## Tools exposed

- `list_chains()` — built-in chain registry
- `abci_info(chain)` — app version, last block, last apphash
- `abci_query(chain, path, data, prove, height)` — read application state
- `get_block(chain, height)` — fetch a block (latest if no height)
- `get_tx(chain, hash)` — fetch a transaction by hash
- `get_validators(chain, height)` — validator set at height
- `chain_status(chain)` — liveness + latest height + apphash
- `sign_query_result(result)` — HMAC-seal for replay-proof attestation

## Safety model

This MCP **cannot move funds** under any circumstances:

- No private key handling
- No `broadcast_tx_*` / `tx_sign` tools exposed
- Signing operations belong in the user's wallet (Keplr, Cosmostation, Leap), never here

## Wire it up

```jsonc
// .mcp.json
{
  "mcpServers": {
    "meok-abci-bridge": {
      "command": "uvx",
      "args": ["meok-abci-bridge-mcp"]
    }
  }
}
```

## Pricing

- Self-host: free (MIT)
- Starter: £29/mo — 10K queries/month + signed attestations
- Pro: £79/mo — 100K queries/month + branded verify URL
- A2A Substrate: £999/mo — bundled with full mesh + identity + payments stack

## Companion MCPs

- `meok-libp2p-agent-mesh-mcp` — peer-to-peer mesh discovery (the layer below)
- `meok-aaif-agent-card-mcp` — AAIF agent identity
- `meok-ap2-mandate-mcp` — Google AP2 v0.2.0 payments
- `agent-handoff-certified-mcp` — signed call-chain proofs

## Legal

Built by [MEOK AI Labs](https://meok.ai) — trading name of CSOAI LTD, UK Companies House 16939677.
Founder: Nicholas Templeman (`nicholas@meok.ai`).
License: MIT.
