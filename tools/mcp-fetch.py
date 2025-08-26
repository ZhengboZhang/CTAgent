import sys
import random
import httpx
import re
from urllib.parse import quote
from mcp.server.fastmcp import FastMCP
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
import requests

mcp = FastMCP("FetchPlus")

class MCP_HTML_Parser(HTMLParser):
    """
    MCP HTML解析器 - 将HTML转换为结构化文本并支持内容提取

    功能特性：
    1. 精准解析HTML为结构化纯文本
    2. 支持CSS选择器/XPath定位元素
    3. 元数据自动提取（标题、描述等）
    4. 保留文档结构（标题层级、列表等）
    5. 安全清理无关标签和脚本
    """

    def __init__(self):
        super().__init__()
        self.reset()
        # 文档结构存储
        self.structured_data = []
        # 当前解析状态
        self.current_tag = None
        self.current_attrs = {}
        self.current_text = ""
        # 元数据存储
        self.metadata = {
            'title': '',
            'description': '',
            'keywords': [],
            'author': ''
        }
        # 结构保留栈
        self.tag_stack = []
        # 选择器配置
        self.selectors = {}

    def reset(self):
        super().reset()
        self.structured_data = []
        self.metadata = {'title': '', 'description': '', 'keywords': [], 'author': ''}
        self.tag_stack = []

    def handle_starttag(self, tag: str, attrs: Dict[str, Optional[str]]):
        self.current_tag = tag.lower()
        self.current_attrs = dict(attrs)
        self.tag_stack.append((tag, attrs))

        # 提取元数据
        if tag == 'meta':
            self._extract_metadata(attrs)
        elif tag == 'title':
            self.current_text = ""

    def handle_endtag(self, tag: str):
        self.tag_stack.pop()
        tag = tag.lower()

        # 处理有文本内容的标签
        if self.current_text.strip():
            content = self._clean_text(self.current_text)

            # 根据标签类型结构化处理
            if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                level = int(tag[1])
                self.structured_data.append(('\n' + '#' * level + ' ' + content, tag))
            elif tag == 'p':
                self.structured_data.append(('\n' + content, tag))
            elif tag == 'li':
                prefix = '- ' if self._in_ordered_list() else '* '
                self.structured_data.append(('\n' + prefix + content, tag))
            elif tag == 'a' and 'href' in self.current_attrs:
                self.structured_data.append((f"[{content}]({self.current_attrs['href']})", tag))
            elif tag == 'title':
                self.metadata['title'] = content

            self.current_text = ""

        self.current_tag = None
        self.current_attrs = {}

    def handle_data(self, data: str):
        if self.current_tag:
            self.current_text += data

    def _in_ordered_list(self) -> bool:
        """检查当前是否在有序列表中"""
        for tag, _ in reversed(self.tag_stack):
            if tag == 'ol':
                return True
            if tag == 'ul':
                return False
        return False

    def _extract_metadata(self, attrs: Dict[str, Optional[str]]):
        """从meta标签提取元数据"""
        attrs_dict = dict(attrs)
        name = attrs_dict.get('name', '').lower()
        content = attrs_dict.get('content', '')

        if name == 'description':
            self.metadata['description'] = content
        elif name == 'keywords':
            self.metadata['keywords'] = [kw.strip() for kw in content.split(',')]
        elif name == 'author':
            self.metadata['author'] = content
        elif 'og:title' in name:
            self.metadata['title'] = content or self.metadata['title']
        elif 'og:description' in name:
            self.metadata['description'] = content or self.metadata['description']

    def _clean_text(self, text: str) -> str:
        """清理文本中的多余空格和特殊字符"""
        text = re.sub(r'\s+', ' ', text)  # 替换多个空白字符
        text = text.strip()
        return text

    def parse(self, html_content: str):
        """解析HTML内容"""
        self.reset()
        self.feed(html_content)
        return self

    def get_structured_text(self) -> str:
        """获取结构化文本"""
        return '\n'.join([item[0] for item in self.structured_data if item[0].strip()])

    def get_metadata(self) -> Dict[str, str]:
        """获取元数据"""
        return self.metadata

    def extract_by_css(self, selector: str) -> List[str]:
        """
        通过CSS选择器提取内容（简化实现）
        实际项目中应使用完整CSS选择器引擎
        """
        # 这里实现基本选择器逻辑
        tag_selectors = re.findall(r'^(\w+)', selector)
        class_selectors = re.findall(r'\.([\w-]+)', selector)
        id_selectors = re.findall(r'#([\w-]+)', selector)

        results = []
        for text, tag in self.structured_data:
            matched = True

            # 标签匹配
            if tag_selectors and tag != tag_selectors[0]:
                matched = False

            # 实际项目中需要完整实现CSS选择器逻辑
            # 这里简化处理仅返回所有段落作为示例
            if matched and tag == 'p':
                results.append(text.strip())

        return results

    def extract_by_xpath(self, xpath: str) -> List[str]:
        """
        通过XPath提取内容（简化实现）
        实际项目中应使用lxml等完整XPath引擎
        """
        # 这里实现基本XPath逻辑
        if xpath == '//title':
            return [self.metadata['title']]
        elif xpath == '//p':
            return [text for text, tag in self.structured_data if tag == 'p']

        return []

@mcp.tool()
def fetch_structured_text(
    url: str,
):

    response = requests.get(url)
    response.encoding = 'utf-8'  
    html_content = response.text

    parser = MCP_HTML_Parser()
    parser.parse(html_content)
    
    return parser.get_structured_text()

@mcp.tool()
def fetch_meta_data(
    url: str,
):
    response = requests.get(url)
    response.encoding = 'utf-8' 
    html_content = response.text

    parser = MCP_HTML_Parser()
    parser.parse(html_content)

    return parser.get_metadata()

@mcp.tool()
def fetch_css(
    url: str,
):
    response = requests.get(url)
    response.encoding = 'utf-8'  
    html_content = response.text

    parser = MCP_HTML_Parser()
    parser.parse(html_content)

    return parser.extract_by_css("p")


if __name__ == "__main__":
    mcp.run(transport="stdio")