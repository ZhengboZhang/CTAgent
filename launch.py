# launch.py
"""
聚合器：自动读取
/mnt/ShareDB_6TB/qiukaixiang/mcp/mcp-client/registry.json
并把其中的 MCP 工具透传到统一的 FastMCP Server。
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters, ClientSession
from contextlib import AsyncExitStack
from pydantic import create_model
from typing import Any

# 固定配置路径
REGISTRY_PATH = Path("/mnt/ShareDB_6TB/qiukaixiang/mcp/mcp-client/registry.json")
TOOLS_DIR = REGISTRY_PATH.parent / "tools"


async def main() -> None:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"❌ registry.json 不存在：{REGISTRY_PATH}")
        return
    except json.JSONDecodeError as e:
        print(f"❌ registry.json 格式错误：{e}")
        return

    if not registry:
        print("⚠️ registry.json 为空")
        return

    aggregate = FastMCP("AggregateServer")

    async with AsyncExitStack() as stack:
        sessions: list[ClientSession] = []

        # 1. 拉起所有子工具进程
        for script in registry:
            script_path = TOOLS_DIR / Path(script).name
            cmd = sys.executable if script_path.suffix == ".py" else "node"
            params = StdioServerParameters(
                command=cmd,
                args=[str(script_path)],
                env=None,
            )

            reader, writer = await stack.enter_async_context(
                stdio_client(params)
            )
            session = await stack.enter_async_context(ClientSession(reader, writer))
            await session.initialize()
            sessions.append(session)

        # 2. 把所有工具透传到聚合器
        for session in sessions:
            tools = (await session.list_tools()).tools
            for t in tools:
                props = t.inputSchema.get("properties", {})
                ToolModel = create_model(
                    t.name + "Args",
                    **{k: (Any, ...) for k in props}
                )

                @aggregate.tool(name=t.name, description=t.description)
                async def _tool(args: ToolModel) -> str:
                    return (
                        await session.call_tool(_tool.name, args.dict())
                    ).content[0].text

        # 3. 启动聚合 Server
        await aggregate.run_stdio_async()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()