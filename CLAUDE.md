# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XianyuAutoAgent is an AI-powered customer service bot for 闲鱼 (Xianyu - Alibaba's second-hand marketplace). It provides 24/7 automated responses with multi-agent routing, smart bargaining, and context-aware conversations.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment (copy .env.example to .env and fill in COOKIES_STR and API_KEY)
cp .env.example .env

# Run the main bot
python main.py
```

## Architecture

### Core Flow
1. `main.py` establishes a WebSocket connection (`wss://wss-goofish.dingtalk.com/`) for real-time messaging
2. Messages are routed through `XianyuLive.handle_message()` which handles both chat and order events
3. `XianyuReplyBot.generate_reply()` generates responses via intent routing

### Multi-Agent System (XianyuAgent.py)
```
User Message → IntentRouter → ClassifyAgent / PriceAgent / TechAgent / DefaultAgent
```
- **IntentRouter**: Three-tier routing - keyword/pattern matching first, then LLM-based ClassifyAgent for ambiguous cases
- **ClassifyAgent**: LLM-based intent classification when rules don't match
- **PriceAgent**: Bargaining scenarios (temperature increases with bargain_count, formula: `min(0.3 + count * 0.15, 0.9)`)
- **TechAgent**: Product technical questions (enables `enable_search` for remote models only)
- **DefaultAgent**: General customer service responses (temperature=0.7)

Context is formatted via `format_history()` which extracts only `user` and `assistant` roles from the message history.

### Model Strategy
- **Remote first**: Uses Bailian (百炼) API by default
- **Local fallback**: Uses Ollama if `USE_LOCAL_MODEL=True` and local is available, as a backup when remote fails
- Remote models support `enable_search=True` for web search; local models do not
- TechAgent automatically uses `enable_search=True` when running on remote models

### Context Management (context_manager.py)
- SQLite database at `data/chat_history.db` stores:
  - `messages` table: chat history per (user_id, item_id, chat_id)
  - `chat_bargain_counts` table: bargaining count per chat session
  - `items` table: cached product information
- Context is retrieved via `get_context_by_chat(chat_id)` and injected into LLM prompts

### Manual Takeover
- Send a message containing `TOGGLE_KEYWORDS` (default: `。`) to switch between AI and manual control per conversation
- State stored in `self.manual_mode_conversations` set

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point, WebSocket connection, message dispatch |
| `XianyuAgent.py` | LLM reply bot, intent routing, agent implementation |
| `XianyuApis.py` | Low-level Xianyu API wrappers (token, item info) |
| `context_manager.py` | SQLite-based chat history and bargain count tracking |
| `listing_bot.py` | Auto-listing and delivery for digital products (Excel-driven) |
| `utils/xianyu_utils.py` | Cookie parsing, signature generation, MessagePack/Base64 decryption |

## Customization

### Prompt Templates
Edit files in `prompts/` directory to customize agent behavior:
- `classify_prompt.txt` - Intent classification
- `price_prompt.txt` - Bargaining agent
- `tech_prompt.txt` - Technical questions
- `default_prompt.txt` - General responses

The bot loads `{name}.txt` if it exists, otherwise falls back to `{name}_example.txt`. Create your custom files to override defaults.

### Safety Filter
All agent responses pass through a safety filter (`_safe_filter`) that blocks contact information (微信, QQ, 支付宝, 银行卡, 线下) and replaces them with a platform safety reminder.

### Auto-Listing (listing_bot.py)
Product data is managed via Excel at `data/products.xlsx` with columns for status, cloud links (Baidu/Quark), delivery message templates, etc. Initialize with:
```bash
python listing_bot.py --init
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COOKIES_STR` | Yes | - | Xianyu cookies from browser |
| `API_KEY` | Yes | - | Bailian API key |
| `MODEL_BASE_URL` | No | dashscope URL | Remote model endpoint |
| `MODEL_NAME` | No | qwen-max | Remote model name |
| `USE_LOCAL_MODEL` | No | False | Enable local Ollama |
| `LOCAL_MODEL_NAME` | No | qwen2.5:7b | Ollama model |
| `TOGGLE_KEYWORDS` | No | 。 | Manual takeover trigger |
| `SIMULATE_HUMAN_TYPING` | No | False | Add typing delay before reply |

## Database Schema

```
messages(user_id, item_id, role, content, timestamp, chat_id)
chat_bargain_counts(chat_id, count, last_updated)
items(item_id, data, price, description, last_updated)
```

## Notes

- Cookies expire and need periodic refresh; the app prompts for new cookies when `get_token` fails with风控 errors
- The `listing_bot.py` module can run independently or be called from `main.py` for order automation
- All timestamps in SQLite are stored in ISO format via `datetime.now().isoformat()`
- Order automation (`do_confirm_and_relist`) runs in a background thread to avoid blocking message processing
