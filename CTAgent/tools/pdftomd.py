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
from PIL import Image
from docx2python import docx2python
import io
import mammoth
import csv
import json

mcp = FastMCP("PDF2MarkdownServer")

def ensure_absolute_path(path: str) -> str:
    """确保路径是绝对路径"""
    if not os.path.isabs(path):
        return os.path.abspath(path)
    return path

@mcp.tool()
def gif_to_jpeg_frames(gif_path: str) -> str:
    """
    读取gif类型的文件，统一转码为 JPEG，保存在 ./temp,然后你应该主动调用load_image工具根据返回的图片路径加载图片，这些图片具有一定连贯性，你解析时要考虑到图片间的联系。
    :param gif_path: 输入 GIF 文件路径
    :return: 一个带有图片路线信息的json格式列表
    """
    try:
        gif_path = Path(gif_path).expanduser().resolve()
        if not gif_path.is_file():
            return json.dumps({"text": f"文件不存在: {gif_path}", "images": []}, ensure_ascii=False)

        out_dir = Path("./temp").expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        with Image.open(gif_path) as im:
            if not im.is_animated:
                return json.dumps({"text": "文件不是动画 GIF", "images": []}, ensure_ascii=False)

            saved = []
            frame_every = 5
            for idx in range(0, im.n_frames, frame_every):
                im.seek(idx)
                rgb = im.convert("RGB")
                jpeg_path = out_dir / f"frame_{idx:04d}.jpeg"
                rgb.save(jpeg_path, "JPEG", quality=95)
                saved.append(str(jpeg_path.resolve()))

        return json.dumps(
            {
                "text": f"已生成 {len(saved)} 张 JPEG，帧间隔 5",
                "images": saved
            },
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps({"text": f"转换失败: {e}", "images": []}, ensure_ascii=False)

@mcp.tool()
def docx_to_markdown(
    docx_path: str,
    fname_base: str = None
) -> str:
    """
    将 DOCX 文件转换为 Markdown，并把所有嵌入图片统一转成 JPEG，存放于 ./temp，使用完这个工具后，请自动使用extract_text_and_images工具提取出md文件中的文字和图片路径，用load_image工具加载图片路径。
    :param docx_path: 输入的 .docx 文件路径
    :param fname_base: 输出文件名前缀（留空时使用原文件名）
    :return: 生成的 .md 文件绝对路径或错误信息
    """
    try:
        docx_path = Path(docx_path).expanduser().resolve()
        if not docx_path.is_file():
            return f"文件不存在: {docx_path}"

        # 1. 输出目录
        output_dir = Path("./temp").expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # 2. 文件名前缀
        base_name = fname_base or docx_path.stem
        md_file = output_dir / f"{base_name}.md"

        # 3. 提取并转码图片
        doc = docx2python(docx_path)
        saved_images = {}  # {原图名: 新图名}
        for idx, (orig_name, img_bytes) in enumerate(doc.images.items(), 1):
            new_name = f"image_{idx}.jpeg"
            jpeg_path = output_dir / new_name
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    im = im.convert("RGB")
                    im.save(jpeg_path, "JPEG", quality=95)
                saved_images[orig_name] = new_name
            except Exception as e:
                print(f"图片转码失败: {orig_name}, {e}", file=sys.stderr)

        # 4. 自定义图片映射
        def convert_image(image):
            # 若找不到 alt_text，默认回到 image_1.jpeg
            return {"src": saved_images.get(image.alt_text, "image_1.jpeg")}

        # 5. DOCX → Markdown
        with docx_path.open("rb") as docx_file:
            result = mammoth.convert_to_markdown(
                docx_file,
                convert_image=mammoth.images.img_element(convert_image)
            )
            md_file.write_text(result.value, encoding="utf-8")

        abs_md = md_file.resolve()
        print(f"[AGENT-CALL] ✅ docx_to_markdown 完成: {docx_path} → {abs_md}", file=sys.stderr)
        return str(abs_md)

    except Exception as e:
        print(f"[AGENT-CALL] ❌ docx_to_markdown 失败: {e}", file=sys.stderr)
        return f"转换失败：{e}"

@mcp.tool()
def csv_to_markdown(
    csv_path: str,
    fname_base: str = None
) -> str:
    """
    将 CSV 文件转换为 Markdown 表格，并存放在 ./temp。之后请主动使用extract_text_and_images读取这个文件，这个文件表示一个表格
    :param csv_path: 输入的 .csv 文件路径
    :param fname_base: 输出文件名前缀（留空时使用原文件名）
    :return: 生成的 .md 文件绝对路径或错误信息
    """

    try:
        csv_path = Path(csv_path).expanduser().resolve()
        if not csv_path.is_file():
            return f"文件不存在: {csv_path}"

        # 1. 输出目录
        output_dir = Path("./temp").expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # 2. 文件名前缀
        base_name = fname_base or csv_path.stem
        md_file = output_dir / f"{base_name}.md"

        # 3. CSV -> Markdown 表格
        md_lines = []
        with csv_path.open(newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:  # 有表头
                md_lines.append("| " + " | ".join(header) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for row in reader:
                md_lines.append("| " + " | ".join(row) + " |")

        # 4. 写入 .md
        md_file.write_text("\n".join(md_lines), encoding="utf-8")

        abs_md = md_file.resolve()
        print(f"[AGENT-CALL] ✅ csv_to_markdown 完成: {csv_path} → {abs_md}", file=sys.stderr)
        return str(abs_md)

    except Exception as e:
        print(f"[AGENT-CALL] ❌ csv_to_markdown 失败: {e}", file=sys.stderr)
        return f"转换失败：{e}"

@mcp.tool()
def pdf_to_markdown(
    pdf_path: str,
    fname_base: str = None
) -> str:
    """
    将 PDF 文件转换为 Markdown/HTML/JSON，，使用完这个工具后，请自动使用extract_text_and_images工具提取出md文件中的文字和图片路径，用load_image工具加载图片路径。。
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
    读取本地任意格式图片/动图，返回对应的 data URL。
    :param path: 本地文件路径（绝对或相对）
    :return:     data:image/xxx;base64,...  或错误提示
    """
    abs_path = ensure_absolute_path(path)
    if not os.path.isfile(abs_path):
        return f"文件不存在: {abs_path}"

    try:
        with Image.open(abs_path) as im:
            # 1. 统一转为 RGB
            im = im.convert("RGB")   
            # 2. 内存 JPEG
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=95)

            jpeg_bytes = buf.getvalue()
    except Exception as e:
        return f"图片处理失败: {e}"

    b64 = base64.b64encode(jpeg_bytes).decode()
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

@mcp.tool()
def read_word_writing_prompt() -> str:
    """
    获取：当用户要求读入word文档时，推荐给模型遵循的工具调用流程提示词，要首先使用这个工具。
    """
    return (
        "当你需要将内容读入（.docx）文档时，请严格按以下流程进行工具调用：\n"
        "1) 首先调用 docx_to_markdown：\n"
        "   - 参数：docx_path(输入word文件路径)，可选fname_base(输出文件名前缀,留空时使用 word 文件名。\n"
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