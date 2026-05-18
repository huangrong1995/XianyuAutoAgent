import pytest

from main import XianyuLive


@pytest.fixture
def live(monkeypatch):
    """创建一个最小化的 XianyuLive 实例"""
    monkeypatch.setenv("COOKIES_STR", "unb=12345; cookie2=abc")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("USE_LOCAL_MODEL", "False")

    from XianyuAgent import XianyuReplyBot
    bot = XianyuReplyBot.__new__(XianyuReplyBot)
    instance = XianyuLive.__new__(XianyuLive)
    instance.manual_mode_conversations = set()
    instance.manual_mode_timestamps = {}
    instance.manual_mode_timeout = 3600
    instance.toggle_keywords = "。"
    instance.message_expire_time = 300000
    instance.myid = "12345"
    return instance


class TestIsChatMessage:
    def test_valid_chat_message(self, live):
        msg = {
            "1": {
                "2": "user@goofish",
                "5": "1234567890000",
                "10": {
                    "reminderTitle": "买家",
                    "senderUserId": "user123",
                    "reminderContent": "你好",
                    "reminderUrl": "https://www.goofish.com/item?id=abc",
                },
            }
        }
        assert live.is_chat_message(msg) is True

    def test_missing_key_1(self, live):
        assert live.is_chat_message({"2": {}}) is False

    def test_missing_key_10(self, live):
        assert live.is_chat_message({"1": {"2": "x"}}) is False

    def test_missing_reminder_content(self, live):
        assert live.is_chat_message({"1": {"10": {"other": "val"}}}) is False

    def test_not_dict(self, live):
        assert live.is_chat_message("string") is False
        assert live.is_chat_message(None) is False
        assert live.is_chat_message(123) is False

    def test_10_not_dict(self, live):
        assert live.is_chat_message({"1": {"10": "not_dict"}}) is False


class TestIsSyncPackage:
    def test_valid_sync_package(self, live):
        msg = {
            "body": {
                "syncPushPackage": {
                    "data": [{"data": "encrypted"}]
                }
            }
        }
        assert live.is_sync_package(msg) is True

    def test_empty_data(self, live):
        msg = {"body": {"syncPushPackage": {"data": []}}}
        assert live.is_sync_package(msg) is False

    def test_missing_body(self, live):
        assert live.is_sync_package({"other": {}}) is False

    def test_not_dict(self, live):
        assert live.is_sync_package("string") is False


class TestIsTypingStatus:
    def test_valid_typing(self, live):
        msg = {"1": [{"1": "user@goofish"}]}
        assert live.is_typing_status(msg) is True

    def test_not_typing(self, live):
        msg = {"1": [{"1": "user@other.com"}]}
        assert live.is_typing_status(msg) is False

    def test_wrong_structure(self, live):
        assert live.is_typing_status({"1": "not_list"}) is False
        assert live.is_typing_status({}) is False


class TestIsSystemMessage:
    def test_system_message(self, live):
        msg = {"3": {"needPush": "false"}}
        assert live.is_system_message(msg) is True

    def test_not_system(self, live):
        assert live.is_system_message({"3": {"needPush": "true"}}) is False
        assert live.is_system_message({}) is False


class TestIsBracketSystemMessage:
    def test_bracket_message(self, live):
        assert live.is_bracket_system_message("[系统消息]") is True
        assert live.is_bracket_system_message("[交易提醒]") is True

    def test_non_bracket(self, live):
        assert live.is_bracket_system_message("普通消息") is False
        assert live.is_bracket_system_message("[不完整") is False

    def test_empty_and_none(self, live):
        assert live.is_bracket_system_message("") is False
        assert live.is_bracket_system_message(None) is False


class TestCheckToggleKeywords:
    def test_matches_keyword(self, live):
        assert live.check_toggle_keywords("。") is True

    def test_no_match(self, live):
        assert live.check_toggle_keywords("你好") is False

    def test_keyword_in_longer_message(self, live):
        # toggle_keywords 是精确匹配，不是子串
        assert live.check_toggle_keywords("好的。") is False


class TestManualMode:
    def test_enter_and_exit(self, live):
        assert live.is_manual_mode("chat1") is False
        live.enter_manual_mode("chat1")
        assert live.is_manual_mode("chat1") is True
        live.exit_manual_mode("chat1")
        assert live.is_manual_mode("chat1") is False

    def test_toggle(self, live):
        result = live.toggle_manual_mode("chat1")
        assert result == "manual"
        assert live.is_manual_mode("chat1") is True

        result = live.toggle_manual_mode("chat1")
        assert result == "auto"
        assert live.is_manual_mode("chat1") is False

    def test_timeout_auto_exit(self, live):
        live.manual_mode_timeout = 0  # 立即超时
        live.enter_manual_mode("chat1")
        import time
        time.sleep(0.01)
        assert live.is_manual_mode("chat1") is False

    def test_independent_chats(self, live):
        live.enter_manual_mode("chat1")
        assert live.is_manual_mode("chat1") is True
        assert live.is_manual_mode("chat2") is False


class TestFormatPrice:
    def test_cents_to_yuan(self, live):
        assert live.format_price(1000) == 10.0
        assert live.format_price(99) == 0.99

    def test_none_returns_zero(self, live):
        assert live.format_price(None) == 0.0

    def test_string_input(self, live):
        assert live.format_price("500") == 5.0

    def test_invalid_returns_zero(self, live):
        assert live.format_price("abc") == 0.0
