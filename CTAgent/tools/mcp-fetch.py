import sys
import random
import httpx
import re
from urllib.parse import quote
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FetchPlus")

# 常用桌面 UA 池，随机挑选
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
]

def clean_url(url: str) -> str:
    """清洗和编码URL"""
    # 移除URL后的多余文字
    cleaned = re.sub(r'\s+.*', '', url)
    
    # 编码特殊字符
    return quote(cleaned, safe='/:?=&')

async def login_and_get_cookie(login_url: str, login_data: dict) -> str:
    """
    模拟登录并获取新的 Cookie
    :param login_url: 登录接口 URL
    :param login_data: 登录数据
    :return: 新的 Cookie
    """
    try:
        # 发送登录请求
        async with httpx.AsyncClient() as client:
            response = await client.post(login_url, data=login_data)
        
        # 检查登录是否成功
        if response.status_code == 200:
            # 获取新的 Cookie
            new_cookie = response.cookies.get("sessionid")
            if new_cookie:
                print(f"登录成功，获取到的 Cookie: {new_cookie}", file=sys.stderr)
                return new_cookie
            else:
                print("登录成功，但未获取到有效的 Cookie", file=sys.stderr)
        else:
            print(f"登录失败，状态码: {response.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"登录过程中发生错误: {e}", file=sys.stderr)
    
    return None

@mcp.tool()
async def fetch(
    url: str,
    login_url: str = "",
    login_data: dict = {},
    timeout: int = 10,
    retries: int = 2,
    user_agent: str = ""
) -> dict:
    """
    获取指定 URL 的原始内容（改进版）
    :param url: 要抓取的网址
    :param login_url: 登录接口 URL（可选）
    :param login_data: 登录数据（可选）
    :param timeout: 超时秒数
    :param retries: 重试次数（含首次）
    :param user_agent: 可选 UA，为空则随机
    :return: 抓取结果
    """
    try:
        # 清洗和编码 URL
        cleaned_url = clean_url(url)
        
        # 如果需要登录，先获取 Cookie
        if login_url and login_data:
            new_cookie = await login_and_get_cookie(login_url, login_data)
            if not new_cookie:
                return {
                    "status": 401,
                    "headers": {},
                    "body": "登录失败，无法获取有效的 Cookie",
                    "success": False
                }
        else:
            new_cookie = None
        
        headers = {
            "User-Agent": user_agent or random.choice(UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.google.com",
            "Connection": "keep-alive"
        }
        if new_cookie:
            headers["Cookie"] = f"sessionid={new_cookie}"
        
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20)
        ) as client:
            attempt = 0
            while attempt < retries:
                try:
                    r = await client.get(cleaned_url, headers=headers)
                    body = r.text[:20_000]
                    print(
                        f"[AGENT-CALL] {'✅' if r.status_code == 200 else '❌'} fetch({cleaned_url}) = {r.status_code} {len(r.content)} bytes (attempt {attempt + 1})",
                        file=sys.stderr
                    )
                    return {
                        "status": r.status_code,
                        "headers": dict(r.headers),
                        "body": body,
                        "success": r.status_code == 200
                    }
                except Exception as e:
                    attempt += 1
                    if attempt >= retries:
                        print(f"[AGENT-CALL] ❌ fetch({cleaned_url}) 失败: {e}", file=sys.stderr)
                        return {
                            "status": 500,
                            "headers": {},
                            "body": f"抓取失败：{e}",
                            "success": False
                        }
    except Exception as e:
        print(f"[AGENT-CALL] ❌ fetch({url}) 失败: {e}", file=sys.stderr)
        return {
            "status": 500,
            "headers": {},
            "body": f"抓取失败：{e}",
            "success": False
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")


'''@mcp.tool()
def read_file(file_path: str) -> dict:
    """
    读取指定文件的内容，并将其转换为 Base64 编码。
    :param file_path: 文件路径
    :return: 文件内容的 Base64 编码
    """
    try:
        with open(file_path, "rb") as file:
            binary_data = file.read()
            base64_encoded_data = base64.b64encode(binary_data).decode("utf-8")
        
        print(
            f"[AGENT-CALL] ✅ read_file({file_path}) = {len(binary_data)} bytes",
            file=sys.stderr
        )
        return {
            "status": 200,
            "content_type": "application/octet-stream",  # 通用二进制文件类型
            "base64_content": base64_encoded_data
        }
    except Exception as e:
        print(f"[AGENT-CALL] ❌ read_file({file_path}) 失败: {e}", file=sys.stderr)
        return {
            "status": 500,
            "content_type": "",
            "base64_content": f"读取文件失败：{e}"
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")'''