#!/usr/bin/env python3
"""
Selenium 登录脚本：打开闲鱼登录页面，等待扫码登录，自动捕获 cookies 并更新 .env
登录后保持浏览器运行，供 listing_bot 连接使用
"""

import os
import sys
import time

# 清除代理设置（Selenium 不需要代理）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

CHROME_BINARY = os.path.expanduser("~/chrome-portable/opt/google/chrome/google-chrome")
CHROMEDRIVER = os.path.expanduser(
    "~/.wdm/drivers/chromedriver/linux64/148.0.7778.167/chromedriver-linux64/chromedriver"
)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(PROJECT_DIR, ".env")
CHROME_PROFILE = os.path.expanduser("~/.xianyu-chrome-profile")
LOGIN_URL = "https://login.taobao.com/member/login.jhtml?style=mini&from=goofish&full_redirect=true"


def update_env_cookies(cookies_str: str):
    """更新 .env 文件中的 COOKIES_STR"""
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if line.strip().startswith("COOKIES_STR="):
                    lines.append(f"COOKIES_STR={cookies_str}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"COOKIES_STR={cookies_str}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)


def main():
    print("=" * 50)
    print("闲鱼扫码登录 - Selenium")
    print("=" * 50)
    print()

    # 使用固定端口，便于 listing_bot 连接
    debug_port = 9222

    print(f"[1/4] 启动 Chrome...")

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1280,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # 使用持久化配置文件，保留登录状态
    options.add_argument(f"--user-data-dir={CHROME_PROFILE}")

    service = Service(CHROMEDRIVER)
    driver = webdriver.Chrome(service=service, options=options)

    # 注入反检测 JS
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    })

    print(f"   Chrome 配置文件: {CHROME_PROFILE}")

    print("[2/4] 打开登录页面...")
    driver.get(LOGIN_URL)
    time.sleep(3)

    print("[3/4] 请扫描二维码登录...")
    print("       等待最多 5 分钟...")
    print()

    start = time.time()
    timeout = 300
    logged_in = False

    while time.time() - start < timeout:
        try:
            current_url = driver.current_url
            if "login" not in current_url.lower() and "member" not in current_url.lower():
                print(f"\n[OK] 登录成功! 当前页面: {current_url}")
                logged_in = True
                break

            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "我的" in body_text and "登录" not in body_text[:50]:
                    print(f"\n[OK] 检测到已登录状态")
                    logged_in = True
                    break
            except:
                pass

            elapsed = int(time.time() - start)
            remaining = timeout - elapsed
            sys.stdout.write(f"\r   已等待 {elapsed}s，剩余 {remaining}s...  ")
            sys.stdout.flush()

        except Exception as e:
            print(f"\n[WARN] 检查状态出错: {e}")

        time.sleep(3)

    print()

    if not logged_in:
        print("[TIMEOUT] 登录超时，请重试")
        driver.quit()
        return 1

    # 导航到闲鱼以获取完整 cookies
    print("[4/4] 获取 cookies...")
    time.sleep(2)
    driver.get("https://www.goofish.com")
    time.sleep(3)

    # 提取 cookies
    cookies = driver.get_cookies()
    cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    if not cookies_str:
        print("[ERROR] 未获取到 cookies")
        driver.quit()
        return 1

    # 更新 .env
    update_env_cookies(cookies_str)

    print()
    print("=" * 50)
    print(f"成功! 已更新 {len(cookies)} 个 cookie 到 .env")
    print(f"文件: {ENV_FILE}")
    print()
    print("浏览器保持运行中，listing_bot 可以直接连接使用")
    print("按 Ctrl+C 关闭浏览器")
    print("=" * 50)

    # 保持浏览器运行
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\n正在关闭浏览器...")
        driver.quit()
        if os.path.exists(DEBUG_PORT_FILE):
            os.remove(DEBUG_PORT_FILE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
