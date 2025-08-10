# -*- coding: utf-8 -*-
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CalculatorServer")

@mcp.tool()
def calculate(expression: str) -> str:
    """
    执行四则运算表达式（+ - * / 和括号）。
    :param expression: 四则运算表达式，如 "3 + 4 * 2"
    :return: 计算结果文本
    """
    try:
        # 安全计算
        result = eval(expression, {"__builtins__": None}, {})
        # 👇 显式日志：让终端一眼看到 Agent 调用了本工具
        print(f"[AGENT-CALL] ✅ 工具 calculate 被调用: {expression} = {result}", file=sys.stderr)
        return f"计算结果：{result}"
    except Exception as e:
        print(f"[AGENT-CALL] ❌ 工具 calculate 调用失败: {e}", file=sys.stderr)
        return f"计算失败：{e}"

if __name__ == "__main__":
    mcp.run(transport='stdio')