import os
import time
import shutil
import subprocess
import platform
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pdf-writer")


# ===== Helpers =====
def _abs(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(_abs(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _wait_for_file(path: str, timeout: float = 20.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        time.sleep(interval)
    return os.path.exists(path)


def _find_soffice() -> Optional[str]:
    # 优先从 PATH 查找
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    # 可在此添加自定义安装路径（若你的环境有固定路径）
    return None


def _convert_docx_to_pdf_linux(src_path: str, dst_pdf: Optional[str]) -> str:
    """
    使用 LibreOffice（soffice --headless）在 Linux 上将 Word (.docx/.doc) 转为 PDF。
    - src_path: 输入 Word 文件路径
    - dst_pdf:  可选，输出 PDF 文件路径；不提供则输出到与源文件同目录同名的 .pdf
    返回：生成的 PDF 绝对路径
    可能抛出：FileNotFoundError, ValueError, RuntimeError
    """
    if platform.system().lower() != "linux":
        raise RuntimeError("This converter is Linux-only. Current system: " + platform.system())

    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError("未找到 LibreOffice（soffice）。请先安装并确保 soffice 在 PATH 中。")

    src = _abs(src_path)
    if not os.path.exists(src):
        raise FileNotFoundError(f"输入文件不存在：{src}")
    if not src.lower().endswith((".docx", ".doc")):
        raise ValueError("输入文件必须为 .docx 或 .doc")

    # LibreOffice 需要输出目录参数；它会在该目录下生成同名 .pdf
    if dst_pdf:
        dst = _abs(dst_pdf)
        if not dst.lower().endswith(".pdf"):
            dst += ".pdf"
        outdir = os.path.dirname(dst) or os.getcwd()
        _ensure_parent_dir(dst)
    else:
        dst = None
        outdir = os.path.dirname(src) or os.getcwd()

    cmd = [
        soffice,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", outdir,
        src,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice 转换失败：{result.stderr or result.stdout}")

    produced_pdf = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if not _wait_for_file(produced_pdf):
        raise RuntimeError(f"LibreOffice 报告成功但未找到 PDF：{produced_pdf}")

    # 若用户指定了自定义输出路径且名称/目录不同，则移动
    if dst and os.path.normcase(produced_pdf) != os.path.normcase(dst):
        # 若目标已存在先删除，以便覆盖
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(produced_pdf, dst)
        return dst

    return produced_pdf


# ===== MCP Tools =====
@mcp.tool()
def convert_docx_to_pdf(
    file_path: str,
    output_pdf_path: Optional[str] = None,
    delete_source: bool = False,
) -> Dict[str, Any]:
    """
    在 Linux 上将 Word 文档（.docx/.doc）转换为 PDF（基于 LibreOffice）。
    - file_path: 输入 .docx/.doc 路径
    - output_pdf_path: 可选，输出 .pdf 路径；不填则与源文件同目录同名
    - delete_source: 若为 True，转换成功后删除源 .docx/.doc
    返回:
      {status, input_docx, output_pdf, deleted_source}
    """
    src = _abs(file_path)
    # 执行转换
    out_pdf = _convert_docx_to_pdf_linux(src, output_pdf_path)

    # 可选：删除源文件
    deleted = False
    deletion_message = ""  # 用于记录删除操作的结果
    if delete_source:
        try:
            # 确保文件路径位于 ./temp 目录下
            temp_dir = os.path.abspath("./temp")
            src_abs = os.path.abspath(src)
            if src_abs.startswith(temp_dir):  # 检查文件是否在 ./temp 目录中
                os.remove(src_abs)
                deleted = True
                deletion_message = f"文件已成功删除：{src_abs}"
            else:
                deletion_message = f"安全警告：试图删除非 ./temp 路径下的文件：{src_abs}"
                deleted = False
        except Exception as e:
            deletion_message = f"删除文件失败：{e}"
            deleted = False  # 保持转换成功，但报告删除失败

    return {
        "status": "ok",
        "input_docx": src,
        "output_pdf": out_pdf,
        "deleted_source": deleted,
        "message": deletion_message
    }


@mcp.tool()
def delete_file(file_path: str) -> Dict[str, Any]:
    """
    删除文件（支持普通文件或符号链接；不删除目录，仅限 ./temp 下的文件）。
    - file_path: 待删除的文件路径
    返回:
      {status, deleted, path, error?}
    """
    path = _abs(file_path)
    temp_dir = os.path.abspath("./temp")  # 确定 ./temp 目录的绝对路径

    try:
        # 检查文件是否位于 ./temp 目录下
        if not os.path.abspath(path).startswith(temp_dir):
            return {
                "status": "error",
                "deleted": False,
                "path": path,
                "error": f"File deletion is restricted to './temp' directory. Attempted path: {path}"
            }

        # 覆盖损坏的符号链接场景
        if not os.path.lexists(path):
            return {"status": "not_found", "deleted": False, "path": path}

        # 若是目录且非符号链接，则拒绝（避免误删目录）
        if os.path.isdir(path) and not os.path.islink(path):
            return {
                "status": "error",
                "deleted": False,
                "path": path,
                "error": "path is a directory; only file/symlink deletion is supported"
            }

        # 尝试删除
        try:
            os.remove(path)
        except PermissionError:
            # 尝试修改权限后再删
            try:
                os.chmod(path, 0o666)
                os.remove(path)
            except Exception as e:
                return {"status": "error", "deleted": False, "path": path, "error": str(e)}
        except FileNotFoundError:
            # 竞争条件：检查时存在，但随后被其他进程删除
            return {"status": "not_found", "deleted": False, "path": path}

        return {"status": "ok", "deleted": True, "path": path}

    except Exception as e:
        return {"status": "error", "deleted": False, "path": path, "error": str(e)}


@mcp.tool()
def get_pdf_workflow_prompt() -> str:
    """
    返回生成PDF文件的推荐工作流提示词。
    """
    return (
        "当你需要输出 PDF 时，请严格遵循以下工作流（先写 Word，再转 PDF）：\n"
        "1) **生成 Word 中间文件**：\n"
        "   - 首先调用 `get_file_path` 生成 Word 文件路径，确保其存储在临时目录（`temp`）。\n"
        "   - 调用示例：\n"
        "       ```python\n"
        "       word_path = get_file_path(type='temp', file_name='example.docx')\n"
        "       ```\n"
        "   - 使用 word-writer 工具链完成文档写作，保持对 `word_path` 的引用：\n"
        "       - 调用 `init_document(word_path, title?, author?)` 初始化文档（如需封面标题可传 title）。\n"
        "       - 调用 `write_title(word_path, text)` 写入封面标题（居中，可选）。\n"
        "       - 调用 `write_heading_level_1/2/3(word_path, text)` 写入各级标题（H1 居中，H2/H3 左对齐）。\n"
        "       - 调用 `write_paragraph(word_path, text, align?, first_line_indent?)` 写入正文。\n"
        "       - 调用 `write_table(word_path, headers, rows, column_widths_cm?, align?)` 写入表格。\n"
        "       - 调用 `write_image(word_path, image_path, width_cm?, caption?, align?)` 插入图片。\n"
        "2) **生成 PDF 文件**：\n"
        "   - 调用 `get_file_path` 为 PDF 文件生成输出路径（`output` 或 `user`）：\n"
        "       ```python\n"
        "       pdf_path = get_file_path(type='output', file_name='example.pdf')\n"
        "       ```\n"
        "       - 若用户指定路径，则使用 `type='user'` 和 `path` 参数生成路径。\n"
        "   - 调用 `convert_docx_to_pdf(word_path, output_pdf_path=pdf_path, delete_source?)` 将 Word 文件转换为 PDF。\n"
        "       - 若希望在转换后删除 Word 文件，请将 `delete_source` 设置为 `True`。\n"
        "3) **回答中需明确以下内容**：\n"
        "   - 已写入的文档内容（如：Title、H1、3 段正文、1 个表格、1 张图片）。\n"
        "   - PDF 的最终输出路径。\n"
        "   - 是否保留了中间的 Word 文件。\n"
        "4) **路径逻辑说明**：\n"
        "   - Word 文件路径：必须存储在临时目录（`temp`，例如 `./temp/document.docx`）。\n"
        "   - PDF 文件路径：\n"
        "       - 默认存储在输出目录（`output`，例如 `./output/document.pdf`）。\n"
        "       - 若用户指定路径，则存储在用户自定义目录（`user`，例如 `/home/user/documents/document.pdf`）。\n"
        "   - 路径生成需调用 `get_file_path`，避免直接传入不安全路径。\n"
        "5) **注意事项**：\n"
        "   - 请确保已安装 LibreOffice 且 `soffice` 命令可用。\n"
    )


if __name__ == "__main__":
    # Run the MCP server over stdio (default for FastMCP)
    mcp.run()