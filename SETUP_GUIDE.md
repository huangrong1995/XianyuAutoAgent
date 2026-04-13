# 闲鱼自动托管工具 - 部署指南

> 基于 [XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent) 项目

---

## 📋 功能概述

| 功能 | 说明 |
|------|------|
| 🤖 AI 自动回复 | 基于 LLM 的智能客服 |
| 📊 多专家系统 | 意图分类 → 价格/技术/客服专家 |
| 💬 上下文管理 | 完整对话历史记忆 |
| 🔄 7×24 值守 | 全天候自动化运营 |
| 💰 智能议价 | 阶梯降价策略 |

---

## 🚀 快速部署

### 环境要求
- Python 3.8+
- 闲鱼账号
- LLM API Key（通义千问/百炼平台）

### 步骤 1：环境配置（已完成）

```bash
cd /home/hrong/workspace/xianyu-autoagent

# 激活虚拟环境
source .venv/bin/activate
```

### 步骤 2：获取配置信息

#### 2.1 获取闲鱼 Cookies

1. 电脑浏览器打开 [闲鱼网页版](https://xianyu.taobao.com/)
2. 登录账号
3. 按 F12 打开开发者工具
4. 切换到 **Network** 标签
5. 刷新页面，点击任意请求
6. 在 **Headers** 中找到 `Cookie` 字段，复制完整内容

#### 2.2 获取通义千问 API Key

1. 访问 [百炼平台](https://bailian.console.aliyun.com/)
2. 创建应用或获取 API Key
3. 记下 API Key

### 步骤 3：配置 .env 文件

编辑 `/home/hrong/workspace/xianyu-autoagent/.env`：

```env
# 必需配置
COOKIES_STR=粘贴你获取的 Cookies
API_KEY=粘贴你的 API Key
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_NAME=qwen-max  # 或 qwen-plus, qwen-turbo

# 可选配置
TOGGLE_KEYWORDS=。  # 输入此字符切换人工/AI模式
SIMULATE_HUMAN_TYPING=False
```

### 步骤 4：启动运行

```bash
cd /home/hrong/workspace/xianyu-autoagent
source .venv/bin/activate
python main.py
```

---

## 📁 项目结构

```
xianyu-autoagent/
├── main.py              # 主程序入口
├── XianyuAgent.py       # AI 回复 Agent 核心逻辑
├── XianyuApis.py        # 闲鱼 API 封装
├── context_manager.py   # 对话上下文管理
├── prompts/            # 提示词模板
│   ├── classify_prompt_example.txt   # 意图分类
│   ├── default_prompt_example.txt   # 默认回复
│   ├── price_prompt_example.txt     # 价格专家
│   └── tech_prompt_example.txt      # 技术专家
├── utils/
│   └── xianyu_utils.py  # 工具函数
├── requirements.txt     # Python 依赖
├── .env                 # 环境配置（敏感）
└── .env.example         # 配置模板
```

---

## 🔧 自定义配置

### 修改提示词

编辑 `prompts/` 目录下的文件：

| 文件 | 用途 | 说明 |
|------|------|------|
| `classify_prompt.txt` | 意图分类 | 决定路由到哪个专家 |
| `default_prompt.txt` | 默认回复 | 通用客服回复 |
| `price_prompt.txt` | 价格专家 | 议价相关问题 |
| `tech_prompt.txt` | 技术专家 | 产品参数问题 |

**使用自定义提示词**：将 `_example` 后缀去掉即可

### 人工接管模式

运行时输入 **句号（。）** 可切换人工/AI模式

---

## ⚠️ 注意事项

1. **Cookies 有效期**：Cookies 会过期，过期后需重新获取
2. **API 费用**：LLM API 调用会产生费用，注意监控
3. **账号安全**：不要分享你的 Cookies 和 API Key
4. **合规使用**：仅供学习交流，勿用于违规用途

---

## 🛠 常见问题

### Q: 启动报错 "Cookie 失效"
**A**: Cookies 已过期，需重新获取（参考步骤 2.1）

### Q: 提示 "API Key 无效"
**A**: 检查 .env 中的 API_KEY 是否正确

### Q: 消息发送失败
**A**: 检查网络连接，或等待一段时间后重试

### Q: 如何停止程序
**A**: 按 Ctrl+C

---

## 📞 技术支持

- 原项目：[GitHub - XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent)
- 问题反馈：在 GitHub Issues 中提交

---

*本文档由 Manus 生成，部署时间：2026-04-11*
