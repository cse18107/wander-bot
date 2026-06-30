# ADR-0002: MCP server as a separate process

**Status:** Accepted

## Context
Travel tools (flights/hotels/activities) could live in-process as plain LangChain
tools, or behind a Model Context Protocol server. MCP is designed around a
client/server boundary.

## Decision
Run a standalone **Wanderbot MCP server** (`mcp_server/`) exposing tools over MCP
(`stdio` locally/tests, streamable HTTP in deployment). The app consumes it via
`MultiServerMCPClient`. The server has its own image (`Dockerfile.mcp`), is
network-isolated by a `NetworkPolicy`, and enforces its own validation + rate limits.

## Consequences
- Pro: real process isolation, independent scaling, reusable by other MCP clients,
  defense-in-depth (guards on both sides).
- Pro: demonstrates correct MCP usage end-to-end.
- Con: an extra network hop and a second deployable; justified by the security
  boundary and reuse.
