import asyncio
import os
import json
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import gradio as gr

# 加载环境变量
load_dotenv()

class MCPGradioClient:
    def __init__(self):
        """初始化集成客户端"""
        self.exit_stack = AsyncExitStack()
        self.api_key = os.getenv("ARK_API_KEY")  # 读取 OpenAI API Key
        self.base_url = os.getenv("ARK_BASE_URL")  # 读取 BASE URL
        self.model = os.getenv("ARK_MODEL")  # 读取 model
        
        if not self.api_key:
            raise ValueError("未找到 API KEY. 请在 .env 文件中配置 OPENAI_API_KEY")

        self.openai_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.sessions: Dict[str, Dict] = {}  # 存储多个服务端会话
        self.tools_map: Dict[str, str] = {}  # 工具映射：工具名称 -> 服务端 ID
        self.conversation_history: List[Dict[str, Any]] = []
        self.current_query = ""
        self.lock = asyncio.Lock()

    async def connect_to_server(self, server_id: str, server_script_path: str):
        """连接到 MCP 服务器"""
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

    async def process_query(self, query: str, temperature, max_length) -> str:
        """处理用户查询并返回响应"""
        async with self.lock:
            self.current_query = query
            messages = self.conversation_history.copy()
            messages.append({"role": "user", "content": query})

            # 构建工具列表
            available_tools = []
            for tool_name, server_id in self.tools_map.items():
                session = self.sessions[server_id]["session"]
                response = await session.list_tools()
                for tool in response.tools:
                    if tool.name == tool_name:
                        available_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema
                            }
                        })

            # 循环处理工具调用
            while True:
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens= max_length,
                    tools=available_tools
                )

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
                        
                        messages.append({
                            "role": "tool",
                            "content": result.content[0].text,
                            "tool_call_id": tool_call.id,
                        })
                
                if not choice.finish_reason == "tool_calls":
                    # 更新对话历史（不含工具调用中间步骤）
                    self.conversation_history.extend([
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": message.content}
                    ])
                    self._trim_history(max_length=10)
                    return message.content

    def _trim_history(self, max_length: int):
        """修剪历史记录"""
        if len(self.conversation_history) > max_length * 2:
            self.conversation_history = self.conversation_history[-max_length * 2:]

    def get_conversation_html(self) -> str:
        """将对话历史格式化为HTML"""
        html = "<div style='font-family: Arial, sans-serif; max-width: 800px; margin: auto;'>"
        for msg in self.conversation_history:
            if msg["role"] == "user":
                html += f"""
                <div style='margin-bottom: 10px;'>
                    <div style='background-color: #f0f7ff; padding: 10px; border-radius: 5px;'>
                        <strong>User:</strong> {msg['content']}
                    </div>
                </div>
                """
            elif msg["role"] == "assistant":
                html += f"""
                <div style='margin-bottom: 20px;'>
                    <div style='background-color: #e8f5e9; padding: 10px; border-radius: 5px;'>
                        <strong>Assistant:</strong> {msg['content']}
                    </div>
                </div>
                """
        html += "</div>"
        return html

    async def clean(self):
        """清理所有资源"""
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools_map.clear()
        self.conversation_history.clear()

async def setup_mcp_client():
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
                        await client.connect_to_server(name, abs_script)
                    except Exception as e:
                        print(f"连接服务器 {name} 失败: {str(e)}")
        
        return client
    
    except Exception as e:
        print(f"初始化失败: {str(e)}")
        await client.clean()
        raise

async def gradio_respond(query: str, client: MCPGradioClient, temperature: float = 0.7, max_length: int = 500):
    """处理Gradio界面提交的查询"""
    if not query.strip():
        return "", client.get_conversation_html()
    
    try:
        response = await client.process_query(query, temperature, max_length)
        return "", client.get_conversation_html()
    except Exception as e:
        error_msg = f"处理查询时出错: {str(e)}"
        client.conversation_history.append(
            {"role": "user", "content": query}
        )
        client.conversation_history.append(
            {"role": "assistant", "content": error_msg}
        )
        return "", client.get_conversation_html()

def create_gradio_interface(client: MCPGradioClient):
    """创建Gradio界面"""
    with gr.Blocks(title="CTAgent", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🛠️ CTAgent")
        gr.Markdown("CTAgent created by CASIA & Tsinghua University")
        
        with gr.Row():
            with gr.Column(scale=3):
                # 对话历史显示
                chat_display = gr.HTML(client.get_conversation_html())
                
                # 用户输入区域
                with gr.Row():
                    user_input = gr.Textbox(
                        placeholder="输入您的问题或指令...",
                        label="用户输入",
                        scale=4,
                        container=False
                    )
                    submit_btn = gr.Button("发送", variant="primary")
                
                # 控制面板
                with gr.Accordion("高级选项", open=False):
                    temperature = gr.Slider(
                        minimum=0,
                        maximum=1,
                        value=0.7,
                        step=0.1,
                        label="温度 (控制随机性)"
                    )
                    max_length = gr.Slider(
                        minimum=100,
                        maximum=1000,
                        value=500,
                        step=50,
                        label="最大生成长度"
                    )
                clear_btn = gr.Button("清空对话历史", variant="stop")
            
            # 右侧信息栏
            with gr.Column(scale=1):
                gr.Markdown("### 已连接工具")
                tools_info = gr.JSON(
                    value={"已连接工具": list(client.tools_map.keys())},
                    label="工具列表"
                )
                
                gr.Markdown("### 使用说明")
                gr.Markdown("- 输入问题后点击发送或按Enter")
                gr.Markdown("- MCP会自动调用合适的工具")
                gr.Markdown("- 清空历史不会断开服务器连接")
        
        # 事件绑定
        submit_btn.click(
            fn=lambda q, temperature, max_length: gradio_respond(q, client, temperature, max_length),
            inputs=[user_input, temperature, max_length],
            outputs=[user_input, chat_display]
        )
        
        user_input.submit(
            fn=lambda q, temperature, max_length: gradio_respond(q, client, temperature, max_length),
            inputs=[user_input, temperature, max_length],
            outputs=[user_input, chat_display]
        )
        
        clear_btn.click(
            fn=lambda: (client.conversation_history.clear(), client.get_conversation_html()),
            inputs=[],
            outputs=[chat_display]
        )
    
    return demo

async def main():
    # 初始化MCP客户端
    client = await setup_mcp_client()
    
    # 创建Gradio界面
    demo = create_gradio_interface(client)
    
    # 启动应用
    demo.launch(server_name="127.0.0.1", server_port=7860)

if __name__ == "__main__":
    asyncio.run(main())