"""
张雪峰人格实现

加载 prompt.txt 作为系统提示词，在需要深度分析时注入 knowledge.md。
使用 skills.py 中的函数进行问题分类、情绪检测和质量自检。

数据流：
    用户文字 → 情绪检测 → 问题分类 → 构建消息 → LLM → 质量自检 → 返回
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml
from loguru import logger

from backend.persona_interface.base_llm import BaseLLM, LLMMessage
from backend.persona_interface.base_persona import BasePersona
from backend.persona_interface.zhangxuefeng.skills import (
    ConversationState,
    ExpressionTier,
    QuestionType,
    check_expression_quality,
    classify_question,
    detect_tier,
    identify_province,
)


class ZhangXuefengPersona(BasePersona):
    """张雪峰人格。

    实现 BasePersona 接口，将张雪峰的思维框架和表达方式
    注入到 LLM 的系统提示词中，使 LLM 以张雪峰的风格回答。

    知识分层策略：
    - 每次对话：加载 prompt.txt（~4KB 核心提示词）
    - 深度分析：追加加载 knowledge.md（~5KB 知识库）
    - 特定问题：从 references/ 检索原始调研资料
    """

    def __init__(self, llm: BaseLLM) -> None:
        """
        Args:
            llm: LLM 后端实例（注入依赖，实现解耦）
        """
        self.name = "zhangxuefeng"
        self._llm = llm

        # 加载的内容
        self._system_prompt: str = ""       # 核心提示词
        self._knowledge: str = ""           # 知识库
        self._persona_config: dict = {}     # persona.yaml 配置
        self._disclaimer: str = ""          # 免责声明

        # 人格文件所在目录
        self._base_dir = Path(__file__).parent

    async def initialize(self) -> None:
        """加载人格配置和提示词。"""
        logger.info("正在加载张雪峰人格...")

        # 1. 加载 persona.yaml
        yaml_path = self._base_dir / "persona.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            self._persona_config = yaml.safe_load(f)

        # 2. 加载 prompt.txt（核心提示词，每次对话必带）
        prompt_path = self._base_dir / "prompt.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_prompt = f.read().strip()
        logger.info(f"核心提示词加载完成: {len(self._system_prompt)} 字符")

        # 3. 加载 knowledge.md（知识库，按需注入）
        knowledge_path = self._base_dir / "knowledge.md"
        with open(knowledge_path, "r", encoding="utf-8") as f:
            self._knowledge = f.read().strip()
        logger.info(f"知识库加载完成: {len(self._knowledge)} 字符")

        # 4. 提取免责声明
        self._disclaimer = self._persona_config.get("disclaimer", "").strip()

        logger.info("张雪峰人格加载完成")

    def get_system_prompt(self) -> str:
        """返回核心系统提示词。"""
        return self._system_prompt

    async def generate_response(
        self, user_text: str, history: list[LLMMessage]
    ) -> str:
        """生成完整回答。

        流程：检测档位 → 判断是否需要知识库 → 构建消息 → LLM → 返回

        Args:
            user_text: 用户问题
            history: 对话历史

        Returns:
            张雪峰风格的回答文本
        """
        # 检测表达档位和问题类型
        tier = detect_tier(user_text)
        question_type = classify_question(user_text)

        # 构建消息列表
        messages = self._build_enhanced_messages(
            user_text, history, tier, question_type
        )

        # 调用 LLM 生成回答
        response = await self._llm.generate(messages)

        logger.info(
            f"张雪峰回答 | 档位={tier.value} | 类型={question_type.value} | "
            f"长度={len(response)}"
        )
        return response

    async def generate_response_stream(
        self, user_text: str, history: list[LLMMessage]
    ) -> AsyncIterator[str]:
        """流式生成张雪峰风格回答。

        首先 yield 免责声明（如果是新对话），然后流式返回 LLM 回答。

        Args:
            user_text: 用户问题
            history: 对话历史

        Yields:
            文本片段
        """
        # 检测档位和问题类型
        tier = detect_tier(user_text)
        question_type = classify_question(user_text)

        logger.info(f"张雪峰流式回答 | 档位={tier.value} | 类型={question_type.value}")

        # 构建消息列表
        messages = self._build_enhanced_messages(
            user_text, history, tier, question_type
        )

        # 流式调用 LLM
        async for chunk in self._llm.generate_stream(messages):
            yield chunk

    def _build_enhanced_messages(
        self,
        user_text: str,
        history: list[LLMMessage],
        tier: ExpressionTier,
        question_type: QuestionType,
    ) -> list[LLMMessage]:
        """构建增强版消息列表。

        根据问题类型和档位，决定是否注入额外知识库内容。

        Args:
            user_text: 用户问题
            history: 对话历史
            tier: 当前表达档位
            question_type: 问题类型

        Returns:
            完整的消息列表
        """
        messages: list[LLMMessage] = []

        # === 系统提示词 ===
        # 核心提示词（每次必带）
        system_content = self._system_prompt

        # 根据问题类型注入额外上下文
        extra_context = []

        # 省份识别：涉及分数/院校的问题附加省份模式说明
        province_info = identify_province(user_text)
        if province_info.is_confirmed:
            from backend.persona_interface.zhangxuefeng.skills import get_gaokao_prompt
            extra_context.append(f"\n【省份信息】{get_gaokao_prompt(province_info)}")

        # 🟢共情档：附加危机处理 SOP
        if tier == ExpressionTier.GREEN:
            hotlines = self._persona_config.get("crisis_hotlines", [])
            if hotlines:
                hotline_text = "、".join(hotlines)
                extra_context.append(
                    f"\n【紧急提醒】用户情绪低落，如涉及自伤倾向必须提供心理援助热线：{hotline_text}"
                )

        # 事实类问题：注入知识库
        if question_type in (QuestionType.FACT_BASED, QuestionType.MIXED):
            extra_context.append(
                f"\n\n【知识库参考】\n{self._knowledge}"
            )

        # 拼接最终系统提示词
        if extra_context:
            system_content += "\n" + "\n".join(extra_context)

        messages.append(LLMMessage(role="system", content=system_content))

        # === 对话历史 ===
        messages.extend(history)

        # === 当前用户问题 ===
        messages.append(LLMMessage(role="user", content=user_text))

        return messages

    async def shutdown(self) -> None:
        """释放资源。"""
        logger.info("张雪峰人格资源已释放")
