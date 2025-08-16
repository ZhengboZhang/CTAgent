import asyncio
import os
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import base64

load_dotenv()

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Ark客户端，从环境变量中读取您的API Key
client = OpenAI(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url=os.getenv("ARK_BASE_URL"),
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改
    api_key= os.getenv("ARK_API_KEY"),
)

image_path = "output/_page_2_Figure_3.jpeg"
base64_image = encode_image(image_path)

response = client.chat.completions.create(
    # 指定您创建的方舟推理接入点 ID，此处已帮您修改为您的推理接入点 ID
    model="ep-20250809212035-dx8wr",
    messages=[
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "图里有什么",
        },
      ],
    },
    {
      "role": "tool",
      "content": [
        {
          "type": "image_url",
          "image_url": {
          "url": f"data:image/jpg;base64,{base64_image}"
          },         
        }
      ]
    }
    ],
    extra_body={
        "thinking": {
            "type": "disabled", 
        }
    },
)
print(response.choices[0])
#f"data:image/jpg;base64,{base64_image}"