FROM python:3.10-slim

# 添加元数据标签
LABEL maintainer="coderxiu<coderxiu@qq.com>"
LABEL description="闲鱼AI客服机器人"
LABEL version="2.0"

# 设置时区和编码
ENV TZ=Asia/Shanghai \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright及其浏览器
RUN pip install --no-cache-dir playwright playwright-stealth \
    && playwright install chromium \
    && playwright install-deps

# 复制应用文件
COPY main.py XianyuAgent.py XianyuApis.py context_manager.py listing_bot.py ./
COPY utils/ utils/

# 复制提示词文件
COPY prompts/classify_prompt_example.txt prompts/classify_prompt.txt
COPY prompts/price_prompt_example.txt prompts/price_prompt.txt
COPY prompts/tech_prompt_example.txt prompts/tech_prompt.txt
COPY prompts/default_prompt_example.txt prompts/default_prompt.txt

# 创建数据目录
RUN mkdir -p data prompts

# 容器启动时运行的命令
CMD ["python", "main.py"]
