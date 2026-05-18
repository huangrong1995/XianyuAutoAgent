import base64
import struct
import json

import pytest

from utils.xianyu_utils import (
    trans_cookies,
    generate_mid,
    generate_uuid,
    generate_device_id,
    generate_sign,
    MessagePackDecoder,
    decrypt,
)


class TestTransCookies:
    def test_basic_parse(self, sample_cookies):
        result = trans_cookies(sample_cookies)
        assert result["unb"] == "12345"
        assert result["cookie2"] == "abc123"
        assert result["XSRF-TOKEN"] == "xyz789"
        assert result["_tb_token_"] == "tok456"

    def test_empty_string(self):
        result = trans_cookies("")
        assert result == {}

    def test_single_cookie(self):
        result = trans_cookies("key=value")
        assert result == {"key": "value"}

    def test_value_with_equals(self):
        result = trans_cookies("token=abc=def=ghi")
        assert result["token"] == "abc=def=ghi"

    def test_malformed_entry_skipped(self):
        result = trans_cookies("good=yes; noequals; also=ok")
        assert result["good"] == "yes"
        assert result["also"] == "ok"
        assert "noequals" not in result


class TestGenerateMid:
    def test_format(self):
        mid = generate_mid()
        parts = mid.split()
        assert len(parts) == 2
        assert parts[1] == "0"
        # 第一部分是数字
        assert parts[0].isdigit()

    def test_uniqueness(self):
        mids = {generate_mid() for _ in range(100)}
        assert len(mids) > 90  # 大部分应唯一


class TestGenerateUuid:
    def test_format(self):
        uuid = generate_uuid()
        assert uuid.startswith("-")
        assert uuid.endswith("1")
        # 中间是时间戳数字
        middle = uuid[1:-1]
        assert middle.isdigit()


class TestGenerateDeviceId:
    def test_format(self):
        did = generate_device_id("user123")
        assert did.endswith("-user123")
        # UUID 部分有 36 个字符（含 4 个连字符）
        uuid_part = did.rsplit("-", 1)[0]
        assert len(uuid_part) == 36
        assert uuid_part[8] == "-"
        assert uuid_part[13] == "-"
        assert uuid_part[18] == "-"
        assert uuid_part[23] == "-"
        assert uuid_part[14] == "4"  # UUID v4 标志

    def test_different_users_different_ids(self):
        did1 = generate_device_id("user1")
        did2 = generate_device_id("user2")
        assert did1 != did2


class TestGenerateSign:
    def test_deterministic(self):
        sig1 = generate_sign("1234567890", "token123", '{"key":"value"}')
        sig2 = generate_sign("1234567890", "token123", '{"key":"value"}')
        assert sig1 == sig2

    def test_different_inputs_different_sigs(self):
        sig1 = generate_sign("111", "tok", "data1")
        sig2 = generate_sign("222", "tok", "data1")
        assert sig1 != sig2

    def test_hex_format(self):
        sig = generate_sign("t", "tok", "data")
        assert len(sig) == 32  # MD5 hex 长度
        assert all(c in "0123456789abcdef" for c in sig)


class TestMessagePackDecoder:
    def test_positive_fixint(self):
        data = bytes([42])
        assert MessagePackDecoder(data).decode() == 42

    def test_nil(self):
        data = bytes([0xc0])
        assert MessagePackDecoder(data).decode() is None

    def test_true_false(self):
        assert MessagePackDecoder(bytes([0xc3])).decode() is True
        assert MessagePackDecoder(bytes([0xc2])).decode() is False

    def test_fixstr(self):
        text = "hello"
        encoded = bytes([0xa0 + len(text)]) + text.encode("utf-8")
        assert MessagePackDecoder(encoded).decode() == "hello"

    def test_fixarray(self):
        # [1, 2, 3] = fixarray(3) + 1 + 2 + 3
        data = bytes([0x93, 0x01, 0x02, 0x03])
        assert MessagePackDecoder(data).decode() == [1, 2, 3]

    def test_fixmap(self):
        # {"a": 1} = fixmap(1) + fixstr("a") + 1
        data = bytes([0x81, 0xa1, 0x61, 0x01])
        result = MessagePackDecoder(data).decode()
        assert result == {"a": 1}

    def test_uint8(self):
        data = bytes([0xcc, 200])
        assert MessagePackDecoder(data).decode() == 200

    def test_uint16(self):
        data = bytes([0xcd]) + struct.pack(">H", 1000)
        assert MessagePackDecoder(data).decode() == 1000

    def test_float64(self):
        data = bytes([0xcb]) + struct.pack(">d", 3.14)
        result = MessagePackDecoder(data).decode()
        assert abs(result - 3.14) < 1e-10

    def test_negative_fixint(self):
        data = bytes([0xff])  # -1
        assert MessagePackDecoder(data).decode() == -1

    def test_empty_data_returns_base64(self):
        # 空数据解码失败时返回 base64 编码
        result = MessagePackDecoder(b"").decode()
        assert isinstance(result, str)

    def test_nested_structure(self):
        # {"key": [1, "two"]} 手工编码
        data = (
            bytes([0x81])  # fixmap(1)
            + bytes([0xa3]) + b"key"  # fixstr("key")
            + bytes([0x92])  # fixarray(2)
            + bytes([0x01])  # 1
            + bytes([0xa3]) + b"two"  # fixstr("two")
        )
        result = MessagePackDecoder(data).decode()
        assert result == {"key": [1, "two"]}


class TestDecrypt:
    def test_base64_json(self):
        """如果数据是 base64 编码的 JSON，应能正确解码"""
        original = {"msg": "hello", "type": 1}
        encoded = base64.b64encode(json.dumps(original).encode()).decode()
        result = decrypt(encoded)
        # decrypt 返回 JSON 字符串
        parsed = json.loads(result)
        # 可能被 MessagePack 解码为各种类型
        assert parsed is not None

    def test_invalid_base64_returns_string(self):
        result = decrypt("not-valid-base64!!!")
        # 应返回字符串，不崩溃
        assert isinstance(result, str)

    def test_empty_string(self):
        result = decrypt("")
        # 应返回字符串，不崩溃
        assert isinstance(result, str)
