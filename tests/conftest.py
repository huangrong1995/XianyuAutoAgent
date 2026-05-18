import os
import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_db(tmp_path):
    """创建临时 SQLite 数据库，返回路径"""
    db_path = str(tmp_path / "test_chat.db")
    return db_path


@pytest.fixture
def tmp_excel(tmp_path):
    """创建临时 Excel 文件路径"""
    return tmp_path / "products.xlsx"


@pytest.fixture
def sample_cookies():
    return "unb=12345; cookie2=abc123; XSRF-TOKEN=xyz789; _tb_token_=tok456"


@pytest.fixture
def sample_product():
    return {
        "row": 2,
        "seq": 1,
        "status": "待上架",
        "item_id": "",
        "title": "测试商品",
        "price": "9.9",
        "desc": "测试描述",
        "img_folder": "",
        "category": "其他",
        "tags": "测试",
        "baidu_link": "https://pan.baidu.com/s/test",
        "quark_link": "",
        "baidu_pwd": "1234",
        "quark_pwd": "",
        "msg_template": "链接：{link}，密码：{password}",
        "sold_count": 0,
        "last_time": "",
    }


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """设置最小化的环境变量"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "COOKIES_STR=unb=12345; cookie2=abc123\n"
        "API_KEY=test-key\n"
    )
    monkeypatch.setenv("COOKIES_STR", "unb=12345; cookie2=abc123")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("USE_LOCAL_MODEL", "False")
    return env_file
