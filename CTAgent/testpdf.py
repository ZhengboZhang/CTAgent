import os
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from marker.output import save_output

# 1. 指定 GPU 和输出目录、输出格式
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
config = ConfigParser({
    "output_dir": "./output",
    "output_format": "markdown"   # 或 "html" / "json"
}).generate_config_dict()

# 2. 创建转换器并转换
converter = PdfConverter(
    artifact_dict=create_model_dict(),
    config=config
)
rendered = converter("./2101.03961v3.pdf")

# 3. 确保输出目录存在
output_dir = "./output"
os.makedirs(output_dir, exist_ok=True)

# 4. 保存（必须给 fname_base）
save_output(
    rendered=rendered,
    output_dir=output_dir,
    fname_base="2101.03961v3"
)