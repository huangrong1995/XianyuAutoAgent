import sqlite3
import json

import pytest

from context_manager import ChatContextManager


class TestChatContextManagerInit:
    def test_creates_db_and_tables(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "messages" in tables
        assert "chat_bargain_counts" in tables
        assert "items" in tables

    def test_wal_mode_enabled(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_creates_directory(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "test.db")
        mgr = ChatContextManager(db_path=db_path)
        import os
        assert os.path.exists(db_path)


class TestSaveAndGetItemInfo:
    def test_save_and_retrieve(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        item_data = {"title": "测试商品", "desc": "描述", "soldPrice": "9.9"}
        mgr.save_item_info("item001", item_data)
        result = mgr.get_item_info("item001")
        assert result["title"] == "测试商品"
        assert result["desc"] == "描述"

    def test_get_nonexistent_returns_none(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        assert mgr.get_item_info("nonexistent") is None

    def test_upsert_updates_existing(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.save_item_info("item001", {"title": "v1", "soldPrice": "10"})
        mgr.save_item_info("item001", {"title": "v2", "soldPrice": "20"})
        result = mgr.get_item_info("item001")
        assert result["title"] == "v2"


class TestAddAndGetContext:
    def test_add_and_retrieve_messages(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.add_message_by_chat("chat1", "user1", "item1", "user", "你好")
        mgr.add_message_by_chat("chat1", "seller1", "item1", "assistant", "你好！")
        context = mgr.get_context_by_chat("chat1")
        assert len(context) == 2
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "你好"
        assert context[1]["role"] == "assistant"
        assert context[1]["content"] == "你好！"

    def test_empty_chat_returns_empty(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        assert mgr.get_context_by_chat("no_such_chat") == []

    def test_messages_ordered_by_timestamp(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.add_message_by_chat("c1", "u1", "i1", "user", "first")
        mgr.add_message_by_chat("c1", "u1", "i1", "user", "second")
        mgr.add_message_by_chat("c1", "u1", "i1", "user", "third")
        context = mgr.get_context_by_chat("c1")
        assert [m["content"] for m in context] == ["first", "second", "third"]

    def test_max_history_trims_old(self, tmp_db):
        mgr = ChatContextManager(max_history=3, db_path=tmp_db)
        for i in range(5):
            mgr.add_message_by_chat("c1", "u1", "i1", "user", f"msg{i}")
        context = mgr.get_context_by_chat("c1")
        assert len(context) <= 3


class TestBargainCount:
    def test_initial_count_is_zero(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        assert mgr.get_bargain_count_by_chat("chat1") == 0

    def test_increment(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.increment_bargain_count_by_chat("chat1")
        assert mgr.get_bargain_count_by_chat("chat1") == 1
        mgr.increment_bargain_count_by_chat("chat1")
        assert mgr.get_bargain_count_by_chat("chat1") == 2

    def test_independent_chats(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.increment_bargain_count_by_chat("chat1")
        mgr.increment_bargain_count_by_chat("chat2")
        mgr.increment_bargain_count_by_chat("chat2")
        assert mgr.get_bargain_count_by_chat("chat1") == 1
        assert mgr.get_bargain_count_by_chat("chat2") == 2

    def test_bargain_count_in_context(self, tmp_db):
        mgr = ChatContextManager(db_path=tmp_db)
        mgr.add_message_by_chat("c1", "u1", "i1", "user", "便宜点")
        mgr.increment_bargain_count_by_chat("c1")
        context = mgr.get_context_by_chat("c1")
        # 最后一条应该是 system 消息含议价次数
        assert context[-1]["role"] == "system"
        assert "议价次数" in context[-1]["content"]
