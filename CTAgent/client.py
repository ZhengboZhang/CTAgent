import asyncio
import os
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

# 加载 .env 文件
load_dotenv()

class MCPClient:
    def __init__(self):
        """初始化 MCP 客户端"""
        self.exit_stack = AsyncExitStack()
        self.api_key = os.getenv("OPENAI_API_KEY_QWEN")  # 读取 OpenAI API Key
        self.base_url = os.getenv("BASE_URL_QWEN")  # 读取 BASE URL
        self.model = os.getenv("MODEL_QWEN")  # 读取 model
       
        if not self.api_key:
            raise ValueError("未找到 API KEY. 请在 .env 文件中配置 API_KEY")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.sessions = {}  # 存储多个服务端会话
        self.tools_map = {}  # 工具映射：工具名称 -> 服务端 ID
        self.conversation_history = []

    async def connect_to_server(self, server_id: str, server_script_path: str):
        """
        连接到 MCP 服务器
        :param server_id: 服务端标识符
        :param server_script_path: 服务端脚本路径
        """
        if server_id in self.sessions:
            raise ValueError(f"服务端 {server_id} 已经连接")

        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 Python 或 JavaScript 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(command=command,
                                              args=[server_script_path],
                                              env=None)

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
   
    async def list_tools(self):
        """列出所有服务端的工具"""
        if not self.sessions:
            print("没有已连接的服务端")
            return

        print("已连接的服务端工具列表:")
        for tool_name, server_id in self.tools_map.items():
            print(f"工具: {tool_name}, 来源服务端: {server_id}")

    async def process_query(self, query: str) -> str:
        """
        调用大模型处理用户查询，并根据返回的 tools 列表调用对应工具。
        支持多次工具调用，直到所有工具调用完成。
        """
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": query})

        # 构建统一的工具列表
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

        #print('整合的服务端工具列表:', available_tools)

        # 循环处理工具调用
        while True:
            # 请求 OpenAI 模型处理
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=available_tools
            )

            # 获取模型返回的消息
            choice = response.choices[0]
            message = choice.message
            
            # ====== 关键修复：添加助手消息 ======
            # 创建助手消息对象
            assistant_msg = {
                "role": "assistant",
                "content": message.content
            }
            
            # 如果有工具调用，添加 tool_calls 字段
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
            
            # 添加到消息历史
            messages.append(assistant_msg)
            # ====== 修复结束 ======

            # 处理返回的内容
            if choice.finish_reason == "tool_calls":
                # 执行工具调用
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    # 根据工具名称找到对应的服务端
                    server_id = self.tools_map.get(tool_name)
                    if not server_id:
                        raise ValueError(f"未找到工具 {tool_name} 对应的服务端")

                    session = self.sessions[server_id]["session"]
                    result = await session.call_tool(tool_name, tool_args)
                    print(f"\n\n[Calling tool {tool_name} on server {server_id} with args {tool_args}]\n\n")

                    # 将工具调用的结果添加到 messages 中
                    messages.append({
                        "role": "tool",
                        "content": result.content[0].text,
                        "tool_call_id": tool_call.id,
                    })
            
            if not choice.finish_reason == "tool_calls":
                # 新增：将本轮完整对话存入历史（不含工具调用中间步骤）
                self.conversation_history.extend([
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": message.content}
                ])
                # 限制历史长度避免过度消耗token
                self._trim_history(max_length=10)
                return message.content

    def _trim_history(self, max_length: int):
        """修剪历史记录，保留最近max_length轮对话"""
        if len(self.conversation_history) > max_length * 2:  # 每轮包含user和assistant两条
            self.conversation_history = self.conversation_history[-max_length * 2:]
   
    async def chat_loop(self):
        """运行交互式聊天循环"""
        print("MCP 客户端已启动！输入 'exit' 退出")
        print("输入 'clear' 可以清空对话历史")  # 新增功能提示

        while True:
            try:
                query = input("问: ").strip()
                if query.lower() == 'exit':
                    break
                # 新增：清空历史命令
                if query.lower() == 'clear':
                    self.conversation_history = []
                    print("已清空对话历史")
                    continue

                response = await self.process_query(query)
                print(f"AI回复: {response}")

            except Exception as e:
                print(f"发生错误: {str(e)}")

    async def clean(self):
        """清理所有资源"""
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools_map.clear()
        self.conversation_history.clear()  # 新增：清理历史记录

async def main():
    # 启动并初始化 MCP 客户端
    client = MCPClient()
    
    try:
        # 1. 加载 JSON 配置文件
        config_path = 'registry.json'  # 配置文件路径
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件 {config_path} 不存在")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # 2. 连接到所有配置的服务器
        for server in config.get("servers", []):
            name = server.get("name")
            script = server.get("script")
            
            if not name or not script:
                print(f"跳过无效的服务器配置: {server}")
                continue
                
            try:
                # 使用绝对路径更安全
                abs_script = os.path.abspath(script)
                if not os.path.exists(abs_script):
                    print(f"警告: 服务器脚本不存在: {abs_script}")
                    continue
                    
                print(f"正在连接服务器: {name} ({abs_script})")
                await client.connect_to_server(name, abs_script)
            except Exception as e:
                print(f"连接服务器 {name} 失败: {str(e)}")
        
        # 3. 列出已连接的工具
        await client.list_tools()
        
        # 4. 运行交互式聊天
        await client.chat_loop()
    
    except Exception as e:
        print(f"程序发生错误: {str(e)}")
    
    finally:
        # 清理资源
        await client.clean()

if __name__ == "__main__":
    asyncio.run(main())