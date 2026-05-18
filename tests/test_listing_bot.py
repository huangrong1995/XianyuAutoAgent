import threading
import time
from unittest.mock import patch, MagicMock

import pytest
import openpyxl

from listing_bot import (
    load_products,
    update_product,
    build_delivery_message,
    parse_cookies,
    load_config,
    create_template_excel,
    _excel_lock,
    do_confirm_and_relist,
)


class TestParseCookies:
    def test_basic_parse(self):
        cookies = parse_cookies("key1=val1; key2=val2")
        assert len(cookies) == 2
        assert cookies[0]["name"] == "key1"
        assert cookies[0]["value"] == "val1"
        assert cookies[0]["domain"] == ".goofish.com"

    def test_empty_string(self):
        assert parse_cookies("") == []

    def test_value_with_equals(self):
        cookies = parse_cookies("token=a=b=c")
        assert cookies[0]["value"] == "a=b=c"


class TestLoadProducts:
    def test_load_from_template(self, tmp_path):
        xlsx = tmp_path / "products.xlsx"
        create_template_excel(xlsx)
        products = load_products(xlsx)
        assert len(products) == 2
        assert products[0]["title"] == "【电子资料】Python编程入门全套视频教程"
        assert products[0]["status"] == "待上架"
        assert products[0]["baidu_pwd"] == "1234"

    def test_nonexistent_file(self, tmp_path):
        assert load_products(tmp_path / "nope.xlsx") == []

    def test_column_count_validation(self, tmp_path):
        """列数不足 16 时应跳过该行"""
        xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["序号", "状态", "商品ID", "标题", "价格"])  # 只有 5 列
        ws.append([1, "待上架", "", "商品", "9.9"])  # 不足 16 列
        wb.save(xlsx)

        products = load_products(xlsx)
        assert len(products) == 0

    def test_skips_empty_rows(self, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        create_template_excel(xlsx)
        # 追加一个空行
        wb = openpyxl.load_workbook(xlsx)
        ws = wb.active
        ws.append([None] * 16)
        wb.save(xlsx)

        products = load_products(xlsx)
        assert len(products) == 2  # 空行被跳过


class TestUpdateProduct:
    def test_update_status(self, tmp_path):
        xlsx = tmp_path / "products.xlsx"
        create_template_excel(xlsx)
        update_product(xlsx, 2, {"status": "已上架", "item_id": "12345"})

        products = load_products(xlsx)
        assert products[0]["status"] == "已上架"
        assert products[0]["item_id"] == "12345"

    def test_update_preserves_other_fields(self, tmp_path):
        xlsx = tmp_path / "products.xlsx"
        create_template_excel(xlsx)
        update_product(xlsx, 2, {"status": "已上架"})

        products = load_products(xlsx)
        assert products[0]["title"] == "【电子资料】Python编程入门全套视频教程"
        assert products[0]["price"] == "9.9"


class TestBuildDeliveryMessage:
    def test_baidu_message(self, sample_product):
        msg = build_delivery_message(sample_product, "baidu")
        assert "https://pan.baidu.com/s/test" in msg
        assert "1234" in msg

    def test_no_link_returns_none(self):
        product = {
            "msg_template": "链接：{link}",
            "baidu_link": "",
            "quark_link": "",
            "baidu_pwd": "",
            "quark_pwd": "",
        }
        assert build_delivery_message(product, "baidu") is None

    def test_quark_message(self):
        product = {
            "msg_template": "链接：{link}，密码：{password}",
            "baidu_link": "",
            "quark_link": "https://pan.quark.cn/s/abc",
            "baidu_pwd": "",
            "quark_pwd": "xyz",
        }
        msg = build_delivery_message(product, "quark")
        assert "https://pan.quark.cn/s/abc" in msg
        assert "xyz" in msg


class TestExcelConcurrency:
    """测试 Excel 读写的线程安全性"""

    def test_sequential_updates_no_crash(self, tmp_path):
        """顺序更新不应出错"""
        xlsx = tmp_path / "products.xlsx"
        create_template_excel(xlsx)

        for i in range(5):
            update_product(xlsx, 2, {"status": f"状态{i}", "sold_count": i})

        products = load_products(xlsx)
        assert len(products) >= 1
        assert products[0]["sold_count"] == 4

    def test_lock_exists(self):
        """验证 Excel 锁已定义"""
        assert _excel_lock is not None
        assert isinstance(_excel_lock, type(threading.Lock()))

    def test_read_after_write_consistent(self, tmp_path):
        """写入后读取数据一致"""
        xlsx = tmp_path / "products.xlsx"
        create_template_excel(xlsx)
        update_product(xlsx, 2, {"status": "已上架", "item_id": "new_id_123"})
        products = load_products(xlsx)
        assert products[0]["status"] == "已上架"
        assert products[0]["item_id"] == "new_id_123"


class TestLoadConfig:
    def test_returns_dict_with_expected_keys(self):
        """load_config 应返回包含必要键的字典"""
        config = load_config()
        assert "cookies_str" in config
        assert "api_key" in config
        assert "model_base_url" in config
        assert "model_name" in config

    def test_loads_from_custom_env(self, monkeypatch, tmp_path):
        import listing_bot
        env_file = tmp_path / ".env"
        env_file.write_text(
            "COOKIES_STR=test_cookies\n"
            "API_KEY=test_api_key\n"
            "MODEL_BASE_URL=https://example.com\n"
            "MODEL_NAME=test-model\n"
        )
        # 清除已加载的环境变量，使 load_dotenv 能读取新值
        monkeypatch.delenv("COOKIES_STR", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("MODEL_BASE_URL", raising=False)
        monkeypatch.delenv("MODEL_NAME", raising=False)
        monkeypatch.setattr(listing_bot, "PROJECT_DIR", tmp_path)
        config = load_config()
        assert config["cookies_str"] == "test_cookies"
        assert config["api_key"] == "test_api_key"


class TestDoConfirmAndRelist:
    """测试 do_confirm_and_relist 发货失败路径"""

    @patch("listing_bot.load_config")
    @patch("listing_bot.parse_cookies")
    @patch("listing_bot.confirm_delivery", return_value=False)
    @patch("listing_bot.get_delivery_message_for_product", return_value="发货消息")
    @patch("listing_bot.relist_with_selenium", return_value="new_item_123")
    @patch("listing_bot.update_product")
    def test_delivery_failure_still_attempts_relist(
        self, mock_update, mock_relist, mock_get_msg, mock_confirm, mock_parse, mock_config
    ):
        """发货失败时仍应尝试重新上架"""
        mock_config.return_value = {"cookies_str": "key=val"}
        mock_parse.return_value = [{"name": "key", "value": "val", "domain": ".goofish.com"}]

        product = {"row": 2, "title": "测试商品", "price": "9.9", "sold_count": 0}
        result = do_confirm_and_relist("item123", "buyer456", product, "chat789")

        # 发货失败但流程继续
        mock_confirm.assert_called_once()
        mock_relist.assert_called_once()
        # 新上架成功，应更新商品
        mock_update.assert_called_once()
        assert result["new_item_id"] == "new_item_123"
        assert result["delivery_msg"] == "发货消息"

    @patch("listing_bot.load_config")
    @patch("listing_bot.parse_cookies")
    @patch("listing_bot.confirm_delivery", return_value=True)
    @patch("listing_bot.get_delivery_message_for_product", return_value="发货消息")
    @patch("listing_bot.relist_with_selenium", return_value="")
    @patch("listing_bot.update_product")
    def test_relist_failure_no_update(
        self, mock_update, mock_relist, mock_get_msg, mock_confirm, mock_parse, mock_config
    ):
        """重新上架失败时不应更新商品状态"""
        mock_config.return_value = {"cookies_str": "key=val"}
        mock_parse.return_value = [{"name": "key", "value": "val", "domain": ".goofish.com"}]

        product = {"row": 2, "title": "测试商品", "price": "9.9", "sold_count": 0}
        result = do_confirm_and_relist("item123", "buyer456", product)

        mock_confirm.assert_called_once()
        mock_relist.assert_called_once()
        # 上架失败，不应更新商品
        mock_update.assert_not_called()
        assert result["new_item_id"] == ""
        assert result["delivery_msg"] == "发货消息"
