import asyncio
import os
import json
from typing import List, Dict, Any
from functools import partial
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import gradio as gr
import threading
from concurrent.futures import ThreadPoolExecutor
import queue

# 加载环境变量
load_dotenv()


class AsyncExecutor:
    """专门处理异步操作的执行器"""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.thread = None
        self.start()

    def start(self):
        """启动异步线程"""

        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

    def run_async(self, coro):
        """在异步线程中运行协程"""
        if not self.loop.is_running():
            self.start()

        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def shutdown(self):
        """关闭执行器"""
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.executor.shutdown()


class MCPGradioClient:
    def __init__(self):
        """初始化集成客户端"""
        self.async_executor = AsyncExecutor()
        self.api_key = os.getenv("ARK_API_KEY")
        self.base_url = os.getenv("ARK_BASE_URL")
        self.model = os.getenv("ARK_MODEL")

        if not self.api_key:
            raise ValueError("未找到 API KEY. 请在 .env 文件中配置 OPENAI_API_KEY")

        self.openai_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.sessions: Dict[str, Dict] = {}
        self.tools_map: Dict[str, str] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        self.current_query = ""
        self.uploaded_files = []
        self.exit_stack = AsyncExitStack()

    def connect_to_server(self, server_id: str, server_script_path: str):
        """同步方式连接到 MCP 服务器"""
        return self.async_executor.run_async(self._connect_to_server_async(server_id, server_script_path))

    async def _connect_to_server_async(self, server_id: str, server_script_path: str):
        """异步连接服务器"""
        if server_id in self.sessions:
            raise ValueError(f"服务端 {server_id} 已经连接")

        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 Python 或 JavaScript 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        # 启动 MCP 服务器并建立通信
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params))
        stdio, write = stdio_transport
        session = await self.exit_stack.enter_async_context(
            ClientSession(stdio, write))

        await session.initialize()
        self.sessions[server_id] = {"session": session, "stdio": stdio, "write": write}
        print(f"已连接到 MCP 服务器: {server_id}")

        # 更新工具映射
        response = await session.list_tools()
        for tool in response.tools:
            self.tools_map[tool.name] = server_id

    def process_uploaded_files(self, files):
        """同步方式处理上传的文件"""
        return self.async_executor.run_async(self._process_uploaded_files_async(files))

    async def _process_uploaded_files_async(self, files):
        """异步处理上传的文件"""
        file_info = []
        for file in files:
            file_path = file.name
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_type = file_name.split('.')[-1].lower()

            info = {
                "文件名": file_name,
                "文件类型": file_type,
                "文件大小": f"{file_size} 字节",
                "文件路径": file_path
            }

            # 添加到上传文件列表
            self.uploaded_files.append(info)
            file_info.append(info)

        return file_info

    def process_query(self, query: str, temperature: float, max_length: int) -> str:
        """同步方式处理用户查询"""
        return self.async_executor.run_async(self._process_query_async(query, temperature, max_length))

    async def _process_query_async(self, query: str, temperature: float, max_length: int) -> str:
        """异步处理用户查询"""
        self.current_query = query

        # 添加上传文件信息到查询中
        if self.uploaded_files:
            file_info = "\n".join([f"{f['文件路径']}" for f in self.uploaded_files])
            enhanced_query = f"请读取文件：'{file_info}'，提取其中的图片和文字，并实现以下指令：\n{query}"
        else:
            enhanced_query = query

        print(enhanced_query)

        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": enhanced_query})

        # 使用预加载的工具列表
        available_tools = self.available_tools

        # 循环处理工具调用
        while True:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_length,
                tools=available_tools
            )

            print(response)

            choice = response.choices[0]
            message = choice.message

            # 添加助手消息到历史
            assistant_msg = {
                "role": "assistant",
                "content": message.content
            }

            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": call.type,
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        }
                    } for call in message.tool_calls
                ]

            print(message)
            messages.append(assistant_msg)

            # 处理工具调用
            if choice.finish_reason == "tool_calls":
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    server_id = self.tools_map.get(tool_name)
                    if not server_id:
                        raise ValueError(f"未找到工具 {tool_name} 对应的服务端")

                    session = self.sessions[server_id]["session"]
                    result = await session.call_tool(tool_name, tool_args)
                    print(f"\n\n[Calling tool {tool_name} on server {server_id} with args {tool_args}]\n\n")

                    messages.append({
                        "role": "tool",
                        "content": result.content[0].text,
                        "tool_call_id": tool_call.id,
                    })

            if not choice.finish_reason == "tool_calls":
                # 更新对话历史（不含工具调用中间步骤）
                self.conversation_history.extend([
                    {"role": "user", "content": enhanced_query},
                    {"role": "assistant", "content": message.content}
                ])
                self._trim_history(max_length=10)
                return message.content

    def list_tools(self):
        """同步方式列出工具"""
        self.async_executor.run_async(self._list_tools_async())

    async def _list_tools_async(self):
        """异步列出工具"""
        if not self.sessions:
            print("没有已连接的服务端")
            return

        print("已连接的服务端工具列表:")
        for tool_name, server_id in self.tools_map.items():
            print(f"工具: {tool_name}, 来源服务端: {server_id}")

    def _trim_history(self, max_length: int):
        """修剪历史记录"""
        if len(self.conversation_history) > max_length * 2:
            self.conversation_history = self.conversation_history[-max_length * 2:]

    def get_conversation_html(self) -> str:
        """将对话历史格式化为HTML"""
        html = "<div style='font-family: Arial, sans-serif; max-width: 800px; margin: auto;'>"
        for msg in self.conversation_history:
            content = msg['content'].replace('\n', '<br>')
            if msg["role"] == "user":
                html += f"""
                <div style='margin-bottom: 10px;'>
                    <div style='background-color: #f0f7ff; padding: 10px; border-radius: 5px;'>
                        <strong>User:</strong> {content}
                    </div>
                </div>
                """
            elif msg["role"] == "assistant":
                html += f"""
                <div style='margin-bottom: 20px;'>
                    <div style='background-color: #e8f5e9; padding: 10px; border-radius: 5px;'>
                        <strong>Assistant:</strong> {content}
                    </div>
                </div>
                """
        html += "</div>"
        return html

    def get_file_preview_html(self) -> str:
        """获取文件预览的HTML"""
        if not self.uploaded_files:
            return "<div style='color: #666; font-style: italic;'>暂无上传文件</div>"

        html = "<div style='font-family: Arial, sans-serif;'>"
        html += "<h4>📁 已上传文件:</h4>"
        for file in self.uploaded_files:
            html += f"""
            <div style='background-color: #f5f5f5; padding: 8px; margin: 5px 0; border-radius: 4px;'>
                📄 {file['文件名']} <span style='color: #666; font-size: 0.9em;'>({file['文件类型']}, {file['文件大小']})</span>
            </div>
            """
        html += "</div>"
        return html

    def clean(self):
        """清理所有资源"""
        self.async_executor.run_async(self._clean_async())
        self.async_executor.shutdown()

    async def _clean_async(self):
        """异步清理资源"""
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools_map.clear()
        self.conversation_history.clear()
        self.uploaded_files.clear()


def setup_mcp_client():
    """初始化MCP客户端并连接服务器"""
    client = MCPGradioClient()

    try:
        # 加载配置文件
        config_path = 'registry.json'
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件 {config_path} 不存在")

        with open(config_path, 'r') as f:
            config = json.load(f)

        # 连接到所有配置的服务器
        for server in config.get("servers", []):
            name = server.get("name")
            script = server.get("script")

            if name and script:
                abs_script = os.path.abspath(script)
                if os.path.exists(abs_script):
                    try:
                        client.connect_to_server(name, abs_script)
                    except Exception as e:
                        print(f"连接服务器 {name} 失败: {str(e)}")

        # 预加载所有工具信息
        client.available_tools = []
        for tool_name, server_id in client.tools_map.items():
            # 这里需要同步获取工具信息
            session_info = client.sessions[server_id]
            response = client.async_executor.run_async(session_info["session"].list_tools())
            for tool in response.tools:
                if tool.name == tool_name:
                    client.available_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.inputSchema
                        }
                    })

        print(f"预加载 {len(client.available_tools)} 个工具")
        return client

    except Exception as e:
        print(f"初始化失败: {str(e)}")
        client.clean()
        raise


def gradio_respond(query: str, temperature: float, max_length: int, client: MCPGradioClient):
    """处理Gradio界面提交的查询"""
    if not query.strip():
        return "", client.get_conversation_html(), client.get_file_preview_html()

    try:
        response = client.process_query(query, temperature, max_length)
        return "", client.get_conversation_html(), client.get_file_preview_html()
    except Exception as e:
        error_msg = f"处理查询时出错: {str(e)}"
        client.conversation_history.append({"role": "user", "content": query})
        client.conversation_history.append({"role": "assistant", "content": error_msg})
        return "", client.get_conversation_html(), client.get_file_preview_html()


def gradio_upload_files(files, client: MCPGradioClient):
    """处理文件上传"""
    if files:
        file_info = client.process_uploaded_files(files)
        return client.get_file_preview_html()
    return client.get_file_preview_html()


def create_gradio_interface(client):
    """创建Gradio界面"""
    with gr.Blocks(title="CTAgent", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🛠️ CTAgent with File Upload")
        gr.Markdown("CTAgent created by CASIA & Tsinghua University - 支持文件上传功能")

        respond_with_client = partial(gradio_respond, client=client)
        upload_with_client = partial(gradio_upload_files, client=client)

        # 界面代码保持不变...
        with gr.Row():
            with gr.Column(scale=3):
                with gr.Row():
                    file_upload = gr.File(
                        file_count="multiple",
                        label="上传文件",
                        file_types=[
                            ".jpg", ".jpeg", ".png", ".gif", ".bmp",
                            ".pdf", ".txt", ".docx", ".csv", ".json"
                        ]
                    )

                file_preview = gr.HTML(client.get_file_preview_html())
                chat_display = gr.HTML(client.get_conversation_html())

                with gr.Row():
                    user_input = gr.Textbox(
                        placeholder="输入您的问题或指令...",
                        label="用户输入",
                        scale=4,
                        container=False
                    )
                    submit_btn = gr.Button("发送", variant="primary")

                with gr.Accordion("高级选项", open=False):
                    temperature = gr.Slider(
                        minimum=0, maximum=1, value=0.7, step=0.1, label="温度 (控制随机性)"
                    )
                    max_length = gr.Slider(
                        minimum=100, maximum=10000, value=2000, step=50, label="最大生成长度"
                    )

                with gr.Row():
                    clear_btn = gr.Button("清空对话历史", variant="stop")
                    clear_files_btn = gr.Button("清空上传文件", variant="secondary")

            with gr.Column(scale=1):
                gr.Markdown("### 已连接工具")
                tools_info = gr.JSON(
                    value={"已连接工具": list(client.tools_map.keys())},
                    label="工具列表"
                )

                gr.Markdown("### 使用说明")
                gr.Markdown("- 支持上传图片、PDF、文档、CSV等文件")
                gr.Markdown("- 上传文件后可以在对话中引用文件内容")
                gr.Markdown("- MCP会自动调用合适的工具处理文件")
                gr.Markdown("- 清空历史不会断开服务器连接")

        # 事件绑定
        submit_btn.click(
            fn=respond_with_client,
            inputs=[user_input, temperature, max_length],
            outputs=[user_input, chat_display, file_preview]
        )

        user_input.submit(
            fn=respond_with_client,
            inputs=[user_input, temperature, max_length],
            outputs=[user_input, chat_display, file_preview]
        )

        file_upload.upload(
            fn=upload_with_client,
            inputs=[file_upload],
            outputs=[file_preview]
        )

        clear_btn.click(
            fn=lambda: (
            client.conversation_history.clear(), client.get_conversation_html(), client.get_file_preview_html()),
            inputs=[],
            outputs=[chat_display, file_preview]
        )

        clear_files_btn.click(
            fn=lambda: (client.uploaded_files.clear(), client.get_file_preview_html()),
            inputs=[],
            outputs=[file_preview]
        )

    return demo


def main():
    # 初始化MCP客户端
    client = setup_mcp_client()
    client.list_tools()

    # 创建Gradio界面
    demo = create_gradio_interface(client)

    # 启动应用
    demo.launch(server_name="127.0.0.1", server_port=7861)

    # 程序退出时清理资源
    client.clean()


if __name__ == "__main__":
    main()