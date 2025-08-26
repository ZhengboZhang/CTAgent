import matplotlib.pyplot as plt
import os
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("plot-tools")

# ===== Helper Function =====
def _save_plot(file_path: str):
    """保存当前绘图到文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    plt.savefig(file_path)
    plt.close()

# ===== MCP Tools =====
@mcp.tool()
def plot_line(
    x: List[float],
    y: List[float],
    file_path: str,
    title: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    绘制折线图。
    注意：所有输入的文本内容（如标题、轴标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - x: x轴数据
    - y: y轴数据
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    - xlabel: x轴标签（必须是英文）
    - ylabel: y轴标签（必须是英文）
    """
    plt.figure()
    plt.plot(x, y, marker="o")
    if title:
        plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "line"}

@mcp.tool()
def plot_bar(
    labels: List[str],
    values: List[float],
    file_path: str,
    title: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    绘制柱状图。
    注意：所有输入的文本内容（如标题、轴标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - labels: 每个柱的标签（必须是英文）
    - values: 每个柱的高度
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    - xlabel: x轴标签（必须是英文）
    - ylabel: y轴标签（必须是英文）
    """
    plt.figure()
    plt.bar(labels, values, color="skyblue")
    if title:
        plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "bar"}

@mcp.tool()
def plot_scatter(
    x: List[float],
    y: List[float],
    file_path: str,
    title: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
    color: Optional[str] = "blue",
) -> Dict[str, Any]:
    """
    绘制散点图。
    注意：所有输入的文本内容（如标题、轴标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - x: x轴数据
    - y: y轴数据
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    - xlabel: x轴标签（必须是英文）
    - ylabel: y轴标签（必须是英文）
    - color: 点的颜色
    """
    plt.figure()
    plt.scatter(x, y, color=color)
    if title:
        plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "scatter"}

@mcp.tool()
def plot_histogram(
    data: List[float],
    bins: int,
    file_path: str,
    title: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    绘制直方图。
    注意：所有输入的文本内容（如标题、轴标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - data: 数据列表
    - bins: 分箱数量
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    - xlabel: x轴标签（必须是英文）
    - ylabel: y轴标签（必须是英文）
    """
    plt.figure()
    plt.hist(data, bins=bins, color="green", alpha=0.7)
    if title:
        plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "histogram"}

@mcp.tool()
def plot_pie(
    labels: List[str],
    values: List[float],
    file_path: str,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    绘制饼图。
    注意：所有输入的文本内容（如标题、标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - labels: 每部分的标签（必须是英文）
    - values: 每部分的值
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    """
    plt.figure()
    plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    if title:
        plt.title(title)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "pie"}

@mcp.tool()
def plot_area(
    x: List[float],
    y: List[float],
    file_path: str,
    title: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    绘制面积图。
    注意：所有输入的文本内容（如标题、轴标签等）必须是英文，非英文内容请模型自行翻译后输入。
    - x: x轴数据
    - y: y轴数据
    - file_path: 保存的图片路径
    - title: 图表标题（必须是英文）
    - xlabel: x轴标签（必须是英文）
    - ylabel: y轴标签（必须是英文）
    """
    plt.figure()
    plt.fill_between(x, y, color="lightblue", alpha=0.5)
    if title:
        plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    _save_plot(file_path)
    return {"status": "ok", "file_path": file_path, "type": "area"}

@mcp.tool()
def get_plot_prompt() -> str:
    """
    获取绘图工具调用流程的指导提示。
    """
    return (
        "在使用绘图工具生成图表时，需严格遵循以下流程和要求：\n\n"
        "1. **绘图工具仅支持英文文本**：\n"
        "   - 所有与图表相关的文本输入（如标题、坐标轴标签、图例等）必须为英文。\n"
        "   - 如果输入包含非英文内容，应在生成图表时将这些内容翻译为英文。\n"
        "   - **翻译范围**：仅限与图表相关的内容（如标题、坐标轴标签、图例等），不干扰其他非图表相关的内容。\n\n"
        "2. **调用路径生成函数**：\n"
        "   - 在绘图前，始终调用 `get_file_path` 函数生成图表的保存路径。\n"
        "   - 参数说明：\n"
        "       - `type`（文件类型）：\n"
        "           - 若为临时图表（仅用于阶段性展示），请设置 `type='temp'`。\n"
        "           - 若为最终输出图表（需要保存到输出路径），请设置 `type='output'`。\n"
        "           - 若用户指定路径，则设置 `type='user'`，并传入 `path` 参数。\n"
        "       - `file_name`（文件名）：图表的文件名，需包含扩展名（如 `.png` 或 `.jpg`）。\n"
        "   - 示例：\n"
        "       ```python\n"
        "       # 临时图表\n"
        "       temp_path = get_file_path(type='temp', file_name='temp_plot.png')\n\n"
        "       # 最终输出图表\n"
        "       output_path = get_file_path(type='output', file_name='final_plot.png')\n\n"
        "       # 用户指定路径\n"
        "       user_path = get_file_path(type='user', file_name='custom_plot.png', path='/home/user/plots')\n"
        "       ```\n\n"
        "3. **绘图工具支持的图表类型**：\n"
        "   - `plot_line`: 绘制折线图。\n"
        "   - `plot_bar`: 绘制柱状图。\n"
        "   - `plot_scatter`: 绘制散点图。\n"
        "   - `plot_histogram`: 绘制直方图。\n"
        "   - `plot_pie`: 绘制饼图。\n"
        "   - `plot_area`: 绘制面积图。\n\n"
        "4. **绘图工具调用流程**：\n"
        "   - 调用绘图工具时，请提供以下必要参数：\n"
        "       - `data`：用于生成图表的核心数据。\n"
        "       - `file_path`：通过 `get_file_path` 函数生成的保存路径。\n"
        "       - 其他可选参数（如标题、坐标轴标签、颜色设置等）。\n"
        "   - 示例：\n"
        "       ```python\n"
        "       plot_line(\n"
        "           x = [1, 2, 3], \n"
        "           y = [4, 5, 6],\n"
        "           file_path=output_path,\n"
        "           title='Example Line Plot',\n"
        "           x_label='X-Axis',\n"
        "           y_label='Y-Axis'\n"
        "       )\n"
        "       ```\n\n"
        "5. **结果说明**：\n"
        "   - 在输出中需明确以下内容：\n"
        "       - 图表类型（如折线图、柱状图等）。\n"
        "       - 图表的保存路径（绝对路径）。\n"
        "       - 图表生成是否成功。\n\n"
        "6. **路径逻辑总结**：\n"
        "   - 临时图表：存储在 `./temp` 目录中，例如 `./temp/temp_plot.png`。\n"
        "   - 最终输出图表：存储在 `./output` 目录中，例如 `./output/final_plot.png`。\n"
        "   - 用户指定路径：存储在用户提供的目录中，例如 `/home/user/plots/custom_plot.png`。\n"
        "   - 路径必须通过 `get_file_path` 函数生成，确保安全性和规范性。\n"
    )

if __name__ == "__main__":
    # Run the MCP server over stdio (default for FastMCP)
    mcp.run()