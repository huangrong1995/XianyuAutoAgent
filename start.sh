#!/bin/bash
set -e

# 安装 Playwright 和 Chromium
pip install --no-cache-dir playwright
playwright install chromium
playwright install-deps

# 启动主程序
exec python main.py "$@"
