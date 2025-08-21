import os
import sys
import base64
import markdown
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from marker.output import save_output

mcp = FastMCP("PDF2MarkdownServer")

def ensure_absolute_path(path: str) -> str:
    """确保路径是绝对路径"""
    if not os.path.isabs(path):
        return os.path.abspath(path)
    return path

@mcp.tool()
def pdf_to_markdown(
    pdf_path: str,
    fname_base: str = None
) -> str:
    """
    将 PDF 文件转换为 Markdown/HTML/JSON。
    :param pdf_path:  输入 PDF 文件路径
    :param fname_base:  输出文件名前缀（留空时使用 PDF 文件名）
    :return: 转换转化成功后的md文档路径或错误信息
    """
    # 确保输入路径是绝对路径
    pdf_path = ensure_absolute_path(pdf_path)
    
    output_dir: str = "./temp"
    output_format = "markdown"
    try:
        # 1. 生成默认文件名前缀
        base_name = fname_base or Path(pdf_path).stem

        # 2. 配置 Marker
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
        config = ConfigParser({
            "output_dir": output_dir,
            "output_format": output_format
        }).generate_config_dict()

        # 3. 创建转换器
        converter = PdfConverter(
            artifact_dict=create_model_dict(),
            config=config
        )

        # 4. 执行转换
        rendered = converter(pdf_path)

        # 5. 确保目录存在
        output_dir = ensure_absolute_path(output_dir)  # 确保输出目录是绝对路径
        os.makedirs(output_dir, exist_ok=True)

        # 6. 保存文件
        save_output(
            rendered=rendered,
            output_dir=output_dir,
            fname_base=base_name
        )

        out_file = Path(output_dir) / f"{base_name}.md"
        abs_out_file = ensure_absolute_path(str(out_file))  # 转换为绝对路径
        
        print(f"[AGENT-CALL] ✅ pdf_to_markdown 完成: {pdf_path} → {abs_out_file}", file=sys.stderr)
        return abs_out_file  # 返回绝对路径

    except Exception as e:
        print(f"[AGENT-CALL] ❌ pdf_to_markdown 失败: {e}", file=sys.stderr)
        return f"转换失败：{e}"

@mcp.tool()
def load_image(path: str) -> str:
    """
    根据本地绝对或相对路径读取图片并返回 data URL，以对图片进行分析和描述。
    :param path:  输入图片文件的绝对或相对路径
    :return:  成功时返回形如 "data:image/jpeg;base64,..." 的 data URL；若文件不存在则返回错误描述
    """
    abs_path = ensure_absolute_path(path)  # 确保是绝对路径
    if not os.path.isfile(abs_path):
        return f"文件不存在: {abs_path}"
    with open(abs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/jpeg;base64,{b64}"

@mcp.tool()
def extract_text_and_images(
    md_path: str
) -> str:
    """
    读取 Markdown 文件，返回清洗后的纯文本和所有图片链接。调用完这个mcptool后，如果存在图片链接，请主动调用load_image加载图片链接
    :param md_path:  Markdown 文件的绝对或相对路径
    :return:  成功时返回 JSON 字符串，包含两个键：
              - "text" : 去除标签、合并空白后的纯文本
              - "images" : 图片链接列表（按出现顺序去重）
              若文件不存在则返回错误描述
    """
    try:
        # 确保路径是绝对路径
        abs_md_path = ensure_absolute_path(md_path)
        
        path = Path(abs_md_path)
        if not path.is_file():
            return f"文件不存在: {abs_md_path}"

        raw = path.read_text(encoding='utf-8')

        # Markdown → HTML
        html = markdown.markdown(raw)

        # 1. 纯文本
        text_only = re.sub(r'<[^>]+>', '', html)
        text_only = re.sub(r'\s+', ' ', text_only).strip()

        # 2. 图片链接 - 转换为绝对路径
        md_imgs = re.findall(r'!\[.*?\]\((.*?)\)', raw)          # 标准 ![alt](url)
        html_imgs = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', html, flags=re.IGNORECASE)
        
        # 去重并保持顺序，同时转换为绝对路径
        md_dir = os.path.dirname(abs_md_path)  # Markdown文件所在目录
        all_links = []
        
        for link in set(md_imgs + html_imgs):  # 先去重
            # 处理相对路径
            if not os.path.isabs(link):
                # 处理相对路径
                abs_link = os.path.normpath(os.path.join(md_dir, link))
                all_links.append(abs_link)
            else:
                all_links.append(link)

        import json
        return json.dumps({"text": text_only, "images": all_links}, ensure_ascii=False)
    except Exception as e:
        return f"处理失败: {e}"

@mcp.tool()
def write_to_file(expression: str, file_path: str) -> str:
    """
    将文本写入指定的txt文件。
    :param expression: 要写入文件的文本内容
    :param file_path: 目标txt文件的路径
    :return: 操作结果文本
    """
    try:
        # 打开文件并写入内容
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(expression)
        # 显式日志：让终端一眼看到 Agent 调用了本工具
        print(f"[AGENT-CALL] ✅ 工具 write_to_file 被调用: 写入文件 {file_path} 成功", file=sys.stderr)
        return f"写入文件 {file_path} 成功"
    except Exception as e:
        print(f"[AGENT-CALL] ❌ 工具 write_to_file 调用失败: {e}", file=sys.stderr)
        return f"写入文件 {file_path} 失败：{e}"
    
@mcp.tool()
def read_pdf_writing_prompt() -> str:
    """
    获取：当用户要求读入pdf文档时，推荐给模型遵循的工具调用流程提示词。
    """
    return (
        "当你需要将内容读入（.pdf）文档时，请严格按以下流程进行工具调用：\n"
        "1) 首先调用 pdf_to_markdown：\n"
        "   - 参数：pdf_path(输入PDF文件路径)，可选fname_base(输出文件名前缀,留空时使用 PDF 文件名。\n"
        "   - 作用：把文档转化为md格式\n"
        "2) 调用extract_text_and_images文档中的字符和图片路径：\n"
        "   - 参数：md_path(输入md文档的路径)。\n"
        "   - 作用：返回md文档中的字符和图片路径。\n"
        "   - 返回：包含文章和图片路径的json格式信息\n"
        "3) 调用load_image工具按之前提取出的图片路径加载图片的base64编码\n"
        "4) 写作规范（默认已在工具中实现）：\n"
        "   - 参数：path(图片路径)中文宋体，英文 Times New Roman。\n"
        "   - 作用：加载图片让agent分析"
    )

if __name__ == "__main__":
    mcp.run(transport='stdio')