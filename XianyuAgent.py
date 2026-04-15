import re
import os
import httpx
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import OpenAI
from loguru import logger

# 加载 .env 环境变量
load_dotenv()


def is_ollama_available() -> bool:
    """检查 Ollama 服务是否可用"""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get("http://localhost:11434/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


class XianyuReplyBot:
    def __init__(self):
        self.use_local = os.getenv("USE_LOCAL_MODEL", "false").lower() == "true"
        self.local_available = False

        # 本地 Ollama 客户端
        self.local_client = None
        self.local_model = os.getenv("LOCAL_MODEL_NAME", "qwen2.5:7b")

        # 远程百炼客户端
        self.remote_client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        self.remote_model = os.getenv("MODEL_NAME", "qwen-max")

        # 检查本地模型可用性
        if self.use_local and is_ollama_available():
            try:
                self.local_client = OpenAI(
                    api_key="ollama",
                    base_url=os.getenv("LOCAL_MODEL_BASE_URL", "http://localhost:11434/v1"),
                )
                # 验证本地模型是否真实存在
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get("http://localhost:11434/api/tags")
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    if any(self.local_model in name for name in model_names):
                        self.local_available = True
                        logger.info(f"✅ 本地模型可用: {self.local_model}")
                    else:
                        logger.warning(f"⚠️ Ollama 运行中但未安装 {self.local_model}，可用模型: {model_names}")
            except Exception as e:
                logger.warning(f"⚠️ 本地模型初始化失败: {e}，将使用远程模型")
        else:
            if self.use_local:
                logger.warning("⚠️ USE_LOCAL_MODEL=True 但 Ollama 不可用，将使用远程模型")
            else:
                logger.info("📡 使用远程模型（百炼）")

        self._init_system_prompts()
        self._init_agents()
        self.router = IntentRouter(self.agents['classify'])
        self.last_intent = None

    def _call_llm(self, messages: List[Dict], temperature: float = 0.4,
                  max_tokens: int = 500, top_p: float = 0.8,
                  extra_body: Optional[dict] = None) -> str:
        """
        调用大模型：远程百炼优先，本地模型兜底
        """
        # 远程优先，本地作为备用
        use_remote = True
        if self.use_local and self.local_available:
            use_remote = False

        # 确定使用的客户端和模型
        if use_remote:
            client = self.remote_client
            model = self.remote_model
            source = "百炼远程"
        else:
            client = self.local_client
            model = self.local_model
            source = f"Ollama本地({model})"

        try:
            if use_remote:
                # 远程调用（百炼）
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                }
                if extra_body:
                    kwargs["extra_body"] = extra_body
                response = client.chat.completions.create(**kwargs)
            else:
                # 本地调用（Ollama OpenAI兼容端点）
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                response = client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            logger.debug(f"LLM调用成功，使用: {source}")
            return content

        except Exception as e:
            # 远程调用失败，尝试本地模型兜底
            if use_remote and self.use_local and self.local_available:
                logger.warning(f"远程模型调用失败: {e}，尝试切换到本地模型")
                try:
                    kwargs = {
                        "model": self.local_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    response = self.local_client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content
                    logger.info(f"✅ 已切换到本地模型 {self.local_model}")
                    return content
                except Exception as local_e:
                    logger.error(f"本地模型调用也失败: {local_e}")
                    raise local_e

            logger.error(f"LLM调用失败: {e}")
            raise

    def _init_agents(self):
        """初始化各领域Agent"""
        self.agents = {
            'classify': ClassifyAgent(self, self.classify_prompt, self._safe_filter),
            'price': PriceAgent(self, self.price_prompt, self._safe_filter),
            'tech': TechAgent(self, self.tech_prompt, self._safe_filter),
            'default': DefaultAgent(self, self.default_prompt, self._safe_filter),
        }

    def _init_system_prompts(self):
        """初始化各Agent专用提示词，优先加载用户自定义文件，否则使用Example默认文件"""
        prompt_dir = "prompts"

        def load_prompt_content(name: str) -> str:
            target_path = os.path.join(prompt_dir, f"{name}.txt")
            if os.path.exists(target_path):
                file_path = target_path
            else:
                file_path = os.path.join(prompt_dir, f"{name}_example.txt")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"已加载 {name} 提示词，路径: {file_path}, 长度: {len(content)} 字符")
                return content

        try:
            self.classify_prompt = load_prompt_content("classify_prompt")
            self.price_prompt = load_prompt_content("price_prompt")
            self.tech_prompt = load_prompt_content("tech_prompt")
            self.default_prompt = load_prompt_content("default_prompt")
            logger.info("成功加载所有提示词")
        except Exception as e:
            logger.error(f"加载提示词时出错: {e}")
            raise

    def _safe_filter(self, text: str) -> str:
        """安全过滤模块"""
        blocked_phrases = ["微信", "QQ", "支付宝", "银行卡", "线下"]
        return "[安全提醒]请通过平台沟通" if any(p in text for p in blocked_phrases) else text

    def format_history(self, context: List[Dict]) -> str:
        """格式化对话历史"""
        user_assistant_msgs = [msg for msg in context if msg['role'] in ['user', 'assistant']]
        return "\n".join([f"{msg['role']}: {msg['content']}" for msg in user_assistant_msgs])

    def generate_reply(self, user_msg: str, item_desc: str, context: List[Dict]) -> str:
        """生成回复主流程"""
        formatted_context = self.format_history(context)

        # 1. 路由决策
        detected_intent = self.router.detect(user_msg, item_desc, formatted_context)

        # 2. 获取对应Agent
        internal_intents = {'classify'}

        if detected_intent == 'no_reply':
            logger.info(f'意图识别完成: no_reply - 无需回复')
            self.last_intent = 'no_reply'
            return "-"
        elif detected_intent in self.agents and detected_intent not in internal_intents:
            agent = self.agents[detected_intent]
            logger.info(f'意图识别完成: {detected_intent}')
            self.last_intent = detected_intent
        else:
            agent = self.agents['default']
            logger.info(f'意图识别完成: default')
            self.last_intent = 'default'

        # 3. 获取议价次数
        bargain_count = self._extract_bargain_count(context)
        logger.info(f'议价次数: {bargain_count}')

        # 4. 生成回复
        return agent.generate(
            user_msg=user_msg,
            item_desc=item_desc,
            context=formatted_context,
            bargain_count=bargain_count
        )

    def _extract_bargain_count(self, context: List[Dict]) -> int:
        for msg in context:
            if msg['role'] == 'system' and '议价次数' in msg['content']:
                try:
                    match = re.search(r'议价次数[:：]\s*(\d+)', msg['content'])
                    if match:
                        return int(match.group(1))
                except Exception:
                    pass
        return 0

    def reload_prompts(self):
        """重新加载所有提示词"""
        logger.info("正在重新加载提示词...")
        self._init_system_prompts()
        self._init_agents()
        logger.info("提示词重新加载完成")


class IntentRouter:
    """意图路由决策器"""

    def __init__(self, classify_agent=None):
        self.rules = {
            'tech': {
                'keywords': ['参数', '规格', '型号', '连接', '对比'],
                'patterns': [r'和.+比']
            },
            'price': {
                'keywords': ['便宜', '价', '砍价', '少点'],
                'patterns': [r'\d+元', r'能少\d+']
            }
        }
        self.classify_agent = classify_agent

    def detect(self, user_msg: str, item_desc, context) -> str:
        """三级路由策略（技术优先）"""
        text_clean = re.sub(r'[^\w\u4e00-\u9fa5]', '', user_msg)

        if any(kw in text_clean for kw in self.rules['tech']['keywords']):
            return 'tech'

        for pattern in self.rules['tech']['patterns']:
            if re.search(pattern, text_clean):
                return 'tech'

        for intent in ['price']:
            if any(kw in text_clean for kw in self.rules[intent]['keywords']):
                return intent
            for pattern in self.rules[intent]['patterns']:
                if re.search(pattern, text_clean):
                    return intent

        if self.classify_agent:
            return self.classify_agent.generate(
                user_msg=user_msg,
                item_desc=item_desc,
                context=context
            )
        return 'default'


class BaseAgent:
    """Agent基类"""

    def __init__(self, bot, system_prompt, safety_filter):
        self.bot = bot
        self.system_prompt = system_prompt
        self.safety_filter = safety_filter

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        messages = self._build_messages(user_msg, item_desc, context)
        response = self._call_llm(messages)
        return self.safety_filter(response)

    def _build_messages(self, user_msg: str, item_desc: str, context: str) -> List[Dict]:
        return [
            {"role": "system", "content": f"【商品信息】{item_desc}\n【你与客户对话历史】{context}\n{self.system_prompt}"},
            {"role": "user", "content": user_msg}
        ]

    def _call_llm(self, messages: List[Dict], temperature: float = 0.4,
                  max_tokens: int = 500, top_p: float = 0.8,
                  extra_body: Optional[dict] = None) -> str:
        return self.bot._call_llm(messages, temperature, max_tokens, top_p, extra_body)


class PriceAgent(BaseAgent):
    """议价处理Agent"""

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        dynamic_temp = min(0.3 + bargain_count * 0.15, 0.9)
        messages = self._build_messages(user_msg, item_desc, context)
        messages[0]['content'] += f"\n▲当前议价轮次：{bargain_count}"

        response = self.bot._call_llm(messages, temperature=dynamic_temp)
        return self.safety_filter(response)


class TechAgent(BaseAgent):
    """技术咨询Agent"""

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        messages = self._build_messages(user_msg, item_desc, context)

        # 百炼 enable_search 仅远程可用
        extra = {"enable_search": True} if (not self.bot.local_available and self.bot.remote_client) else None
        response = self.bot._call_llm(messages, temperature=0.4, extra_body=extra)
        return self.safety_filter(response)


class ClassifyAgent(BaseAgent):
    """意图识别Agent"""

    def generate(self, **args) -> str:
        response = super().generate(**args)
        return response


class DefaultAgent(BaseAgent):
    """默认处理Agent"""

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0) -> str:
        messages = self._build_messages(user_msg, item_desc, context)
        response = self.bot._call_llm(messages, temperature=0.7)
        return self.safety_filter(response)
