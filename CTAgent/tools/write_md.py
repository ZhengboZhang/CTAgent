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
      - dir: 目标目录（相对或绝对路径）。未提供时使用 ./output（若不存在会自动创建）。
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
    base_dir = Path(dir).expanduser() if dir else Path("./output")
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

@mcp.tool()
def get_markdown_writing_prompt() -> str:
    """
    获取：当用户要求写入 Markdown 文件时，推荐给模型遵循的工具调用流程提示词。
    """
    return (
        "当你需要将内容写入 Markdown (.md) 文件时，请严格按以下流程进行工具调用：\n"
        "1) **路径生成**：首先调用路径生成函数 `get_file_path` 来确定文件的保存路径。\n"
        "   - 参数说明：\n"
        "       - type（文件类型）：可选 'temp'（临时文件）或 'output'（最终输出文件）。\n"
        "       - file_name（文件名）：用户指定的文件名（可不含 .md 后缀）。\n"
        "       - path（可选，用户自定义路径）：仅当 type 为 'user' 时使用。\n"
        "   - 返回值：根据参数生成的最终文件路径。例如：\n"
        "       - 若 type='temp' 且 file_name='notes.md'，返回 './temp/notes.md'。\n"
        "       - 若 type='output' 且 file_name='report.md'，返回 './output/report.md'。\n"
        "       - 若 type='user' 且 path='/home/user/docs'，返回 '/home/user/docs/notes.md'。\n"
        "2) **调用 `write_to_markdown` 写入内容**：\n"
        "   - 参数：\n"
        "       - content：Markdown 格式的字符串内容。\n"
        "       - dir：调用 `get_file_path` 返回的路径中提取的目录部分。\n"
        "       - filename：调用 `get_file_path` 返回的路径中提取的文件名部分。\n"
        "       - overwrite：是否允许覆盖已存在文件（默认为 False）。\n"
        "   - 示例：\n"
        "       ```python\n"
        "       file_path = get_file_path(type='output', file_name='example.md')\n"
        "       dir, filename = os.path.split(file_path)\n"
        "       write_to_markdown(content='这是一个示例内容', dir=dir, filename=filename, overwrite=False)\n"
        "       ```\n"
        "3) **写入行为与结果说明**：\n"
        "   - 默认行为：若未提供 `dir` 参数，Markdown 文件将写入 `./output` 目录。\n"
        "   - 文件名清理：文件名会自动清理非法字符，确保安全性和规范性。\n"
        "   - 文件覆盖：若 `overwrite` 为 False，自动避免覆盖同名文件，通过追加后缀（如 `-1`, `-2`）生成唯一文件名。\n"
        "   - 自动创建目录：若目标目录不存在，会自动创建。\n"
        "4) **输出结果**：在工具的输出中清楚说明以下内容：\n"
        "   - 写入的文件路径（绝对路径）。\n"
        "   - 实际使用的目录。\n"
        "   - 文件名及是否覆盖已有文件。\n"
        "   - 写入的字节数。\n"
        "   - 本次调用是否创建了新目录。\n"
        "5) **追加内容或修改文档**：若用户要求追加内容或修改已存在文档，保持对同一文件路径的引用，确保一致性。\n"
    )

if __name__ == "__main__":
    # 运行 MCP 服务器
    mcp.run()