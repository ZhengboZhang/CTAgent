# -*- coding: utf-8 -*-
"""
mcp-fetch
一个只负责“把 URL 抓回来”的极简 MCP 工具。
职责：HTTP GET → 返回原始内容（字节 + headers），不做任何解析。
"""
import sys
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FetchServer")

@mcp.tool()
async def fetch(url: str, timeout: int = 10) -> str:
    """
    获取指定 URL 的原始内容。
    :param url: 要抓取的网址
    :param timeout: 超时秒数，默认 10 秒
    :return: 抓取结果（状态码 + 前 20 KB 正文）
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20)
        ) as client:
            r = await client.get(url, headers={"User-Agent": "MCP-Fetch/1.0"})
        body = r.text[:20_000]  # 截断防止超大页面
        print(
            f"[AGENT-CALL] ✅ fetch({url}) = {r.status_code} {len(r.content)} bytes",
            file=sys.stderr
        )
        return {
            "status": r.status_code,
            "headers": dict(r.headers),
            "body": body
        }
    except Exception as e:
        print(f"[AGENT-CALL] ❌ fetch({url}) 失败: {e}", file=sys.stderr)
        return {
            "status": 500,
            "headers": {},
            "body": f"抓取失败：{e}"
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")