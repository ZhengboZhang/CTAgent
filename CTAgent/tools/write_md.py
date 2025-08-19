from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("md-writer")


def _sanitize_filename(name: str) -> str:
    # 去除空字节与首尾空白
    name = name.strip().replace("\x00", "")
    # 屏蔽路径分隔符，避免跨目录
    name = name.replace("/", "_").replace("\\", "_")
    # 替换控制字符
    name = re.sub(r"[\r\n\t]", "_", name)
    # 仅保留常见安全字符
    name = re.sub(r"[^A-Za-z0-9._ \-\(\)\[\]]", "_", name)
    # 合并多余下划线
    name = re.sub(r"_{2,}", "_", name)
    return name or "untitled"


@mcp.tool()
async def write_to_markdown(
    content: str,
    dir: str | None = None,
    filename: str | None = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    将内容写入 Markdown (.md) 文件。

    参数:
      - content: 要写入的 Markdown 文本内容。
      - dir: 目标目录（相对或绝对路径）。未提供时使用 ./Outputs（若不存在会自动创建）。
      - filename: 文件名（可不含 .md 后缀）。未提供时使用时间戳生成。
      - overwrite: 为 True 则允许覆盖同名文件；为 False 时若存在同名文件，会自动追加 -1、-2 等后缀避免覆盖。

    返回:
      - path: 写入文件的绝对路径。
      - dir: 实际使用的目录绝对路径。
      - filename: 最终使用的文件名。
      - bytes_written: 写入的字节数。
      - overwritten: 是否覆盖了已存在的文件。
      - created_dir: 本次调用是否创建了目录。
    """
    # 1) 解析与创建目录
    base_dir = Path(dir).expanduser() if dir else Path("./Outputs")
    existed_before = base_dir.exists()
    base_dir.mkdir(parents=True, exist_ok=True)
    created_dir = not existed_before

    # 2) 生成/清洗文件名，并确保 .md 后缀
    if not filename or not filename.strip():
        fname = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    else:
        # 只取文件名部分，避免传入路径干扰
        fname = Path(filename).name

    fname = _sanitize_filename(fname)
    if not fname.lower().endswith(".md"):
        fname = f"{fname}.md"

    target = base_dir / fname

    # 3) 确定最终写入路径（处理覆盖/去重）
    overwritten = False
    if target.exists():
        if overwrite:
            overwritten = True
            final_path = target
        else:
            stem, suffix = target.stem, target.suffix
            i = 1
            while True:
                candidate = base_dir / f"{stem}-{i}{suffix}"
                if not candidate.exists():
                    final_path = candidate
                    break
                i += 1
    else:
        final_path = target

    # 4) 写入内容（UTF-8）
    data = content if content is not None else ""
    # 确保父目录存在（极少数并发情况下的安全网）
    final_path.parent.mkdir(parents=True, exist_ok=True)
    with open(final_path, "w", encoding="utf-8", newline="\n") as f:
        bytes_written = f.write(data)

    result = {
        "path": str(final_path.resolve()),
        "dir": str(base_dir.resolve()),
        "filename": final_path.name,
        "bytes_written": bytes_written,
        "overwritten": overwritten,
        "created_dir": created_dir,
    }
    return result


if __name__ == "__main__":
    # 运行 MCP 服务器
    mcp.run()