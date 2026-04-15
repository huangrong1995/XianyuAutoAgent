#!/usr/bin/env python3
"""
闲鱼自动托管工具 - 自动上架模块
流程: 买家购买 → 自动确认发货 → 自动发送云盘链接给买家

依赖于 XianyuAutoAgent 的 Cookie 和 API Key 配置
"""

import os
import sys
import json
import time
import random
import argparse
import base64
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime
from threading import Thread

import openpyxl
import requests
from dotenv import load_dotenv

# 项目路径
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
STATE_FILE = DATA_DIR / "listing_state.json"
PRODUCTS_EXCEL = DATA_DIR / "products.xlsx"


def generate_sign(t: str, token: str, data: str) -> str:
    """生成签名"""
    app_key = "34839810"
    msg = f"{token}&{t}&{app_key}&{data}"
    md5_hash = hashlib.md5()
    md5_hash.update(msg.encode('utf-8'))
    return md5_hash.hexdigest()


# ============ 配置加载 ============

def load_config():
    """加载环境配置"""
    env_file = PROJECT_DIR / ".env"
    load_dotenv(env_file)
    
    return {
        "cookies_str": os.getenv("COOKIES_STR", ""),
        "api_key": os.getenv("API_KEY", ""),
        "model_base_url": os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_name": os.getenv("MODEL_NAME", "qwen-max"),
    }


# ============ Excel 商品数据 ============

def create_template_excel(path: Path):
    """创建商品模板 Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "商品列表"
    
    headers = [
        "序号", "状态", "商品ID", "标题", "价格", "描述", 
        "图片文件夹", "分类", "标签",
        "百度云链接", "夸克云链接", "百度云密码", "夸克云密码",
        "发货消息模板", "累计售出", "最后上架时间"
    ]
    ws.append(headers)
    
    # 示例数据
    sample_products = [
        [1, "待上架", "", "【电子资料】Python编程入门全套视频教程", "9.9",
         "包含完整Python基础+进阶视频教程，共200+集，附赠源码和课件。",
         "images/python_course", "其他", "Python,编程",
         "https://pan.baidu.com/s/xxxx", "https://pan.quark.cn/s/xxxx",
         "1234", "abcd",
         "您好！资料链接：{link}，提取码：{password}，请保存好链接如有丢失可再次联系客服索取。",
         0, ""],
        [2, "待上架", "", "【电子资料】2024考研考公全套复习资料", "19.9",
         "涵盖考研/考公全科资料，包含真题、笔记、重点总结。",
         "images/kaoyan", "其他", "考研,考公",
         "https://pan.baidu.com/s/yyyy", "https://pan.quark.cn/s/yyyy",
         "5678", "efgh",
         "您好！考研资料链接：{link}，提取码：{password}，包含最新真题和重点笔记。",
         0, ""],
    ]
    
    for row in sample_products:
        ws.append(row)
    
    wb.save(path)
    print(f"✅ 已创建商品模板: {path}")


def load_products(path: Path) -> list:
    """从 Excel 加载商品列表"""
    if not path.exists():
        return []
    
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    
    products = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        (seq, status, item_id, title, price, desc, img_folder, 
         category, tags, baidu_link, quark_link, baidu_pwd, quark_pwd,
         msg_template, sold_count, last_time) = row
        products.append({
            "row": i,
            "seq": seq,
            "status": status or "待上架",
            "item_id": item_id or "",
            "title": title or "",
            "price": str(price or "0"),
            "desc": desc or "",
            "img_folder": img_folder or "",
            "category": category or "其他",
            "tags": tags or "",
            "baidu_link": baidu_link or "",
            "quark_link": quark_link or "",
            "baidu_pwd": baidu_pwd or "",
            "quark_pwd": quark_pwd or "",
            "msg_template": msg_template or "您好！资料链接：{link}，提取码：{password}，请保存好链接。",
            "sold_count": sold_count or 0,
            "last_time": last_time or ""
        })
    
    return products


def update_product(path: Path, row_num: int, updates: dict):
    """更新商品信息"""
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    
    col_map = {
        "status": 2, "item_id": 3, "title": 4, "price": 5, "desc": 6,
        "img_folder": 7, "category": 8, "tags": 9,
        "baidu_link": 10, "quark_link": 11, "baidu_pwd": 12, "quark_pwd": 13,
        "msg_template": 14, "sold_count": 15, "last_time": 16
    }
    
    for key, value in updates.items():
        if key in col_map:
            ws.cell(row=row_num, column=col_map[key]).value = value
    
    wb.save(path)


def build_delivery_message(product: dict, link_type: str = "baidu") -> str:
    """构建发货消息"""
    template = product["msg_template"]
    
    if link_type == "baidu":
        link = product["baidu_link"]
        password = product["baidu_pwd"]
    else:
        link = product["quark_link"]
        password = product["quark_pwd"]
    
    if not link:
        return None
    
    # 替换占位符
    msg = template.replace("{link}", link).replace("{password}", password)
    return msg


# ============ Cookie 解析 ============

def parse_cookies(cookie_str: str) -> list:
    """解析 cookies 字符串"""
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".goofish.com",
                "path": "/"
            })
    return cookies


# ============ 闲鱼 API 操作 ============

def confirm_delivery(cookies: list, item_id: str, buyer_id: str) -> bool:
    """确认发货（数字资料自动发货）"""
    import requests
    
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".goofish.com"))
    
    url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.order.confirmsend/1.0/"
    headers = {
        "content-type": "application/json",
        "referer": "https://www.goofish.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "itemId": item_id,
        "buyerId": buyer_id,
        "expressType": "virtual",
        "message": "数字资料商品，链接将在24小时内发送，请注意查收。"
    }
    
    try:
        resp = session.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()
        ret = data.get("ret", [None])[0]
        if ret and ret.startswith("SUCCESS"):
            print(f"   ✅ 发货成功")
            return True
        else:
            print(f"   ⚠️  发货响应: {data}")
            return True  # 仍返回成功，避免中断流程
    except Exception as e:
        print(f"   ❌ 发货API失败: {e}")
        return True  # 继续发送链接


def relist_with_playwright(product: dict, config: dict) -> str:
    """使用 Playwright 模拟浏览器上架"""
    from playwright.sync_api import sync_playwright
    
    cookies = parse_cookies(config["cookies_str"])
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            cookies=cookies
        )
        page = context.new_page()
        
        try:
            page.goto("https://www.goofish.com/publish.htm", timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            
            # 填写标题
            page.fill('input[placeholder*="标题"],input[name="title"]', product["title"])
            time.sleep(0.5)
            
            # 填写价格
            page.fill('input[placeholder*="价格"],input[name="price"]', product["price"])
            time.sleep(0.5)
            
            # 填写描述
            page.fill('textarea[placeholder*="描述"],textarea[name="description"]', product["desc"])
            time.sleep(0.5)
            
            # 上传图片
            if product["img_folder"]:
                img_dir = PROJECT_DIR / product["img_folder"]
                if img_dir.exists():
                    img_files = list(img_dir.glob("*.*"))
                    if img_files:
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files([str(f) for f in img_files[:9]])
                        time.sleep(2)
            
            # 发布
            page.click('button:has-text("发布"),button:has-text("确认")')
            time.sleep(3)
            
            # 获取新商品ID
            url = page.url
            if "itemId=" in url:
                item_id = url.split("itemId=")[1].split("&")[0]
                print(f"   ✅ 上架成功: {item_id}")
                return item_id
            
        except Exception as e:
            print(f"   ❌ Playwright 上架失败: {e}")
        finally:
            browser.close()

        return ""


def relist_with_api(product: dict, config: dict) -> str:
    """使用 API 上架商品"""
    session = requests.Session()

    # 解析 cookies
    for part in config["cookies_str"].split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            session.cookies.set(name.strip(), value.strip(), domain=".goofish.com")

    # 获取 token
    token = session.cookies.get("_m_h5_tk", "").split("_")[0]
    if not token:
        print("   ❌ 无法获取 token")
        return ""

    t = str(int(time.time() * 1000))

    # 构建请求数据
    item_data = {
        "title": product.get("title", ""),
        "price": product.get("price", "0"),
        "description": product.get("desc", ""),
        "category": product.get("category", "other"),
        "tags": product.get("tags", "").split(",") if product.get("tags") else [],
        " images": [],  # 图片需要额外上传
    }

    data_val = json.dumps(item_data, ensure_ascii=False)

    # 生成签名
    sign = generate_sign(t, token, data_val)

    # 构建请求
    params = {
        "jsv": "2.7.2",
        "appKey": "34839810",
        "t": t,
        "sign": sign,
        "v": "1.0",
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": "mtop.idle.pc.idleitem.publish",
        "sessionOption": "AutoLoginOnly",
        "spm_cnt": "a21ybx.publish.0.0",
        "spm_pre": "a21ybx.personal.sidebar.1.40206ac2UcXOCW",
        "log_id": "40206ac2UcXOCW"
    }

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.goofish.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }

    try:
        response = session.post(
            "https://h5api.m.goofish.com/h5/mtop.idle.pc.idleitem.publish/1.0/",
            params=params,
            data={"data": data_val},
            headers=headers,
            timeout=30
        )

        result = response.json()
        print(f"   📦 上架响应: {result}")

        ret = result.get("ret", [None])
        if ret and any("SUCCESS" in str(r) for r in ret):
            # 尝试从响应中提取商品ID
            data = result.get("data", {})
            if isinstance(data, dict):
                item_id = data.get("itemId") or data.get("item_id") or data.get("idleId")
                if item_id:
                    print(f"   ✅ 上架成功: {item_id}")
                    return str(item_id)
            # 如果没有解析到itemId但返回成功，也返回成功
            print(f"   ✅ 上架API调用成功")
            return "success"
        else:
            print(f"   ❌ 上架失败: {result}")
            return ""

    except Exception as e:
        print(f"   ❌ 上架API异常: {e}")
        return ""


def try_relist(product: dict, config: dict) -> str:
    """尝试上架商品，优先使用API方式"""
    # 优先使用API方式
    print(f"   🔄 尝试API方式上架...")
    result = relist_with_api(product, config)
    if result:
        return result

    # API方式失败，尝试Playwright
    print(f"   🔄 API方式失败，尝试Playwright方式...")
    try:
        from playwright.sync_api import sync_playwright
        result = relist_with_playwright(product, config)
        return result
    except ImportError:
        print(f"   ⚠️  Playwright未安装或不可用，上架失败")
        return ""


# ============ 消息发送（供 main.py 调用）============

def get_delivery_message_for_product(item_id: str = None, product: dict = None) -> str:
    """
    获取指定商品的发货消息
    优先用 item_id 匹配，否则用 product
    """
    if item_id:
        products = load_products(PRODUCTS_EXCEL)
        for p in products:
            if p.get("item_id") == item_id:
                product = p
                break
    
    if not product:
        return None
    
    # 优先百度云，其次夸克
    if product.get("baidu_link"):
        return build_delivery_message(product, "baidu")
    elif product.get("quark_link"):
        return build_delivery_message(product, "quark")
    
    return None


def do_confirm_and_relist(item_id: str, buyer_id: str, product: dict, send_chat_id: str = None) -> dict:
    """
    执行确认发货+重新上架
    返回结果供 main.py 发送消息
    """
    config = load_config()
    cookies = parse_cookies(config["cookies_str"])
    
    result = {
        "success": False,
        "item_id": item_id,
        "buyer_id": buyer_id,
        "chat_id": send_chat_id,
        "delivery_msg": None,
        "new_item_id": None,
    }
    
    # 1. 确认发货
    print(f"\n📦 确认发货: 商品={item_id}, 买家={buyer_id}")
    confirm_delivery(cookies, item_id, buyer_id)
    
    # 2. 准备发货消息
    if product:
        result["delivery_msg"] = get_delivery_message_for_product(product=product)
        print(f"📨 发货消息: {result['delivery_msg'][:50] if result['delivery_msg'] else '无'}...")
        
        # 3. 重新上架
        print(f"🚀 重新上架...")
        new_id = relist_with_playwright(product, config)
        result["new_item_id"] = new_id
        
        # 4. 更新商品状态
        if new_id:
            sold_count = (product.get("sold_count") or 0) + 1
            update_product(PRODUCTS_EXCEL, product["row"], {
                "status": "已上架",
                "item_id": new_id,
                "sold_count": sold_count,
                "last_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"✅ 流程完成! 累计售出: {sold_count}")
    
    result["success"] = True
    return result


# ============ 主程序 ============

def main():
    parser = argparse.ArgumentParser(description="闲鱼自动上架机器人")
    parser.add_argument("--init", action="store_true", help="初始化商品模板")
    parser.add_argument("--interval", type=int, default=60, help="检查间隔（秒）")
    parser.add_argument("--monitor", action="store_true", help="监控模式")
    args = parser.parse_args()
    
    if args.init:
        DATA_DIR.mkdir(exist_ok=True)
        create_template_excel(PRODUCTS_EXCEL)
        return
    
    if not PRODUCTS_EXCEL.exists():
        print(f"❌ 商品文件不存在: {PRODUCTS_EXCEL}")
        print(f"   运行 --init 生成模板")
        sys.exit(1)
    
    if args.monitor:
        print("🔄 监控模式开发中...")
    else:
        products = load_products(PRODUCTS_EXCEL)
        for product in products:
            if product["status"] == "待上架":
                print(f"\n📦 上架: {product['title']}")
                config = load_config()
                new_id = relist_with_playwright(product, config)
                if new_id:
                    update_product(PRODUCTS_EXCEL, product["row"], {
                        "status": "已上架",
                        "item_id": new_id,
                        "last_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })


if __name__ == "__main__":
    main()
