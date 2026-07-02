"""MCP Client — wraps MCP protocol for connecting to MCP Servers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from tool.base import ToolMeta, ToolResult

logger = logging.getLogger(__name__)


class MCPClient:
    """Connects to an MCP Server, discovers tools, and forwards calls.

    Supports stdio transport (spawns child process) and SSE/HTTP transport.
    """

    def __init__(self, server_config: dict) -> None:
        self._config = server_config
        self._name = server_config.get("name", "unknown")
        self._transport = server_config.get("transport", "stdio")
        self._tools: dict[str, dict] = {}  # name -> tool schema
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._tool_filter: set[str] | None = None

        # Tool whitelist from config
        if "tools" in server_config:
            self._tool_filter = set(server_config["tools"])

    async def connect(self) -> None:
        """Connect to the MCP Server."""
        if self._transport == "stdio":
            await self._connect_stdio()
        else:
            raise ValueError(f"Unsupported MCP transport: {self._transport}")

        # Initialize handshake with timeout
        await asyncio.wait_for(
            self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "resumeast", "version": "1.0.0"},
            }),
            timeout=10.0,
        )

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # Discover tools
        await self._discover_tools()

        self._connected = True
        logger.info("MCP Client '%s' connected, %d tools available", self._name, len(self._tools))

    async def _connect_stdio(self) -> None:
        """Connect via stdio transport (child process)."""
        command = self._config.get("command", "")
        args = self._config.get("args", [])
        env = self._config.get("env", {})

        if not command:
            raise ValueError(f"MCP Server '{self._name}' has no command configured")

        # Resolve env vars
        resolved_env = {**os.environ}
        # Remove proxy env vars that might interfere with subprocess
        for key in list(resolved_env.keys()):
            if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
                del resolved_env[key]
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                resolved_env[key] = os.environ.get(env_var, "")
            else:
                resolved_env[key] = str(value)

        # Spawn process
        self._process = await asyncio.create_subprocess_exec(
            command, *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=resolved_env,
        )

        # Drain stderr in background to prevent pipe buffer deadlock
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        self._reader = self._process.stdout
        self._writer = self._process.stdin

        # Start background reader
        self._read_task = asyncio.create_task(self._read_loop())

    async def _drain_stderr(self) -> None:
        """Read and discard stderr to prevent pipe buffer deadlock."""
        try:
            while self._process and self._process.returncode is None:
                await self._process.stderr.readline()
        except Exception:
            pass

    async def _read_loop(self) -> None:
        """Background task to read JSON-RPC responses from the server."""
        try:
            while self._process and self._process.returncode is None:
                line = await self._reader.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue

                # Handle response
                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(
                            MCPError(msg["error"].get("message", "Unknown error"))
                        )
                    else:
                        future.set_result(msg.get("result", {}))

        except Exception as e:
            logger.error("MCP read loop error: %s", e)
        finally:
            self._connected = False

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and wait for response."""
        self._request_id += 1
        msg_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future

        data = json.dumps(msg) + "\n"
        self._writer.write(data.encode("utf-8"))
        await self._writer.drain()

        return await asyncio.wait_for(future, timeout=30.0)

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        data = json.dumps(msg) + "\n"
        self._writer.write(data.encode("utf-8"))
        await self._writer.drain()

    async def _discover_tools(self) -> None:
        """Discover available tools from the MCP Server."""
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])

        for tool_def in tools:
            name = tool_def.get("name", "")
            # Apply whitelist filter
            if self._tool_filter and name not in self._tool_filter:
                continue
            self._tools[name] = {
                "name": name,
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("inputSchema", {}),
            }

    def get_tool_metas(self) -> list[dict]:
        """Return discovered tools as dicts compatible with ToolRegistry."""
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> ToolResult:
        """Call a tool on the MCP Server."""
        if not self._connected:
            return ToolResult.err(
                code="not_connected",
                message=f"MCP Server '{self._name}' is not connected",
                summary="MCP not connected",
            )

        if name not in self._tools:
            return ToolResult.err(
                code="tool_not_found",
                message=f"Tool '{name}' not found on MCP Server '{self._name}'",
                summary="Tool not found",
            )

        try:
            result = await self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            })

            # Parse MCP result
            content = result.get("content", [])
            is_error = result.get("isError", False)

            if is_error:
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                return ToolResult.err(
                    code="mcp_tool_error",
                    message="\n".join(text_parts),
                    summary="Tool execution failed",
                )

            # Extract text content
            text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            result_text = "\n".join(text_parts)

            return ToolResult.ok(
                data={"result": result_text},
                summary=result_text[:200] if result_text else "No result",
            )

        except asyncio.TimeoutError:
            return ToolResult.err(
                code="timeout",
                message=f"Tool '{name}' timed out on MCP Server '{self._name}'",
                summary="Tool timeout",
            )
        except MCPError as e:
            return ToolResult.err(
                code="mcp_error",
                message=str(e),
                summary="MCP error",
            )
        except Exception as e:
            logger.error("MCP tool call error: %s", e)
            return ToolResult.err(
                code="error",
                message=str(e),
                summary="Tool call failed",
            )

    async def close(self) -> None:
        """Close the MCP connection and clean up."""
        self._connected = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()

        self._process = None
        self._reader = None
        self._writer = None
        logger.info("MCP Client '%s' closed", self._name)

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


class MCPError(Exception):
    """Error from MCP protocol."""
    pass
