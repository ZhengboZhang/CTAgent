import asyncio
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json, pathlib
from temp_manager import TempManager
from vllm import LLM, SamplingParams
import uuid
from transformers import AutoTokenizer
from pathlib import Path

# 加载 .env 文件
load_dotenv()

class MCPClient:
    def __init__(self):
        """初始化 MCP 客户端"""
        self.exit_stack = AsyncExitStack()
        self.api_key = os.getenv("ARK_API_KEY", True)  # 读取 OpenAI API Key
        self.base_url = os.getenv("ARK_BASE_URL")  # 读取 BASE URL
        self.model = os.getenv("ARK_MODEL")  # 读取 model
        self.pipelines = json.loads(pathlib.Path("pipelines.json").read_text(encoding="utf-8"))
       
        if not self.api_key:
            raise ValueError("未找到 API KEY. 请在 .env 文件中配置 API_KEY")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        self.use_local = os.getenv("USE_LOCAL_AGENT", "false").lower() == "true"

        # 0.3 初始化 vLLM 引擎（仅在开关开启时）
        if self.use_local:
            self.router_engine = LLM(
                model=os.getenv("ROUTER_MODEL_PATH", "Qwen/Qwen2.5-7B-Instruct"),
                dtype="float16",
                max_model_len=2048,
                gpu_memory_utilization=0.5,
                trust_remote_code=True,
            )
            self.router_tokenizer = AutoTokenizer.from_pretrained(
                os.getenv("ROUTER_MODEL_PATH", "Qwen/Qwen2.5-7B-Instruct"),
                trust_remote_code=True,
            )
        # 0.4 其余成员
        self.exit_stack = AsyncExitStack()
        self.sessions = {}  # 存储多个服务端会话
        self.tools_map = {}  # 工具映射：工具名称 -> 服务端 ID
        self.conversation_history = []
        self.image_queue = []
        self.conversation_history.append({"role": "system", 
            "content": "你是一个熟练的文档分析助手。请直接给出最终答案，不要展示思考过程或中间步骤。我给你配备了很多mcptool。当给你提供文档地址并让你分析时你会先使用pdf_to_markdown工具将其转化为md格式，然后使用extract_text_and_images工具解析转化而得的md文档中的文字和图片地址，接下来你会使用load_image加载图片链接，记住，当你给文档时你会查找是否有图片链接，如果有无论问题如何都要使用load_image加载图片"}
                                        )
        self.temp_mgr = TempManager(root="temp", max_mb=300, ttl_sec=3600)
        self.recent_questions: List[str] = []
        self.temp_mgr.clear_all() 

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
    

    async def router_llm(self, messages: list,
                        available_tools: list,
                        threshold: float = 0.5) -> list[str]:
        """
        7 B 置信度打分路由：逐个工具链给出 0–1 分，≥阈值入选，并展开工具链
        """
        if not self.use_local:
            return []

        user_turn = messages[-1]["content"]
        selected_tools = []
        
        history_q = "\n".join(f"- {q}" for q in self.recent_questions)

        # 构建工具链描述
        pipeline_descriptions = []
        for pipeline_name, pipeline_info in self.pipelines.items():
            pipeline_descriptions.append({
                "name": pipeline_name,
                "description": pipeline_info["desc"]
            })

        # 对每个工具链打分
        for pipeline in pipeline_descriptions:
            name = pipeline["name"]
            desc = pipeline["description"]

            prompt = (
                "<|im_start|>system\n"
                "You are a relevance scorer. Given user questions (including previous rounds) and a tool pipeline, "
                "output a single float between 0 and 1 indicating how helpful the pipeline is.\n"
                "0 = no help, 1 = essential. Only output the number.\n"
                "<|im_end|>\n"
                "<|im_start|>user\n"
                f"Recent questions:\n{history_q}\n\n"
                f"Current question: {user_turn}\n"
                f"Pipeline: {name}\n"
                f"Description: {desc}\n"
                "<|im_end|>\n"
                "<|im_start|>assistant\n"
            )

            sampling = SamplingParams(max_tokens=5,   # 足够输出 "0.83"
                                    temperature=0.0,
                                    stop=["\n", " "])
            outs = self.router_engine.generate([prompt], sampling, use_tqdm=False)

            try:
                score = float(outs[0].outputs[0].text.strip())
            except ValueError:
                score = 0.0

            if score >= threshold:
                selected_tools.extend(self.pipelines[name]["tools"])

        # 去重：保留工具链顺序，去掉重复工具
        seen = set()
        final_selected_tools = []
        for tool in selected_tools:
            if tool not in seen:
                seen.add(tool)
                final_selected_tools.append(tool)

        return final_selected_tools

    async def process_query(self, query: str) -> str:
            messages = self.conversation_history.copy()
            if query:
                messages.append({"role": "user", "content": query})
                self.recent_questions.append(query)
                self.recent_questions = self.recent_questions[-5:] 

            available_tools = []
            for tool_name, server_id in self.tools_map.items():
                session = self.sessions[server_id]["session"]
                for tool in (await session.list_tools()).tools:
                    if tool.name == tool_name:
                        available_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema
                            }
                        })

            # 如果启用路由模型，则根据路由模型的打分选择工具
            if self.use_local:
                candidates = await self.router_llm(messages, available_tools)  # List[str]
                if candidates:
                    available_tools = [t for t in available_tools if t["function"]["name"] in candidates]

            # 如果关闭路由模型，直接使用所有工具
            while True:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=available_tools,
                    temperature=0.3,  # 直接传递所有工具
                    extra_body={"thinking": {"type": "enabled"}}
                )
                choice = response.choices[0]
                message = choice.message

                assistant_msg = {"role": "assistant", "content": message.content}
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

                if choice.finish_reason == "tool_calls":
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        server_id = self.tools_map.get(tool_name)
                        if not server_id:
                            raise ValueError(f"未找到工具 {tool_name} 对应的服务端")

                        session = self.sessions[server_id]["session"]
                        result = await session.call_tool(tool_name, tool_args)
                        print(f"\n[Calling tool {tool_name} | {tool_args}]\n")

                        if tool_name == "load_image":
                            self.image_queue.append(result.content[0].text)
                        else:
                            messages.append({
                                "role": "tool",
                                "content": result.content[0].text,
                                "tool_call_id": tool_call.id,
                            })

                        if self.image_queue:
                            for img_data in self.image_queue:
                                messages.append({
                                    "role": "user",
                                    "content": [{"type": "image_url", "image_url": {"url": img_data}}]
                                })
                            self.image_queue = []

                else:
                    filtered = [m for m in messages if m["role"] != "tool"]
                    self.conversation_history.extend(filtered)
                    self._trim_history(max_length=20)
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
                self.temp_mgr.cleanup()

            except Exception as e:
                print(f"发生错误: {str(e)}")

    async def clean(self):
        """清理所有资源"""
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools_map.clear()
        self.conversation_history.clear()  # 新增：清理历史记录
        self.temp_mgr.clear_all()

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