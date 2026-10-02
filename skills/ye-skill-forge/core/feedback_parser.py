#!/usr/bin/env python3
"""
反馈解析器 - 核心改进功能
"""

import json
import re
from pathlib import Path


class FeedbackParser:
    """
    解析各种形式的用户反馈
    支持：文本、文件引用、对话记录、使用样本
    """

    def __init__(self):
        self.feedback = {
            "issues": [],      # 问题列表
            "examples": [],    # 使用案例
            "good": [],        # 好的做法（应保留）
            "suggestions": []  # 改进建议
        }

    def parse(self, inputs, base_dir="."):
        """
        统一解析入口

        Args:
            inputs: 可以是字符串、字符串列表、或混合
            base_dir: 文件引用的基础目录

        Returns:
            解析后的反馈字典
        """
        if isinstance(inputs, str):
            inputs = [inputs]

        for input_item in inputs:
            # 处理文件引用（@filename）
            if self._is_file_reference(input_item):
                file_path = self._resolve_file_path(input_item, base_dir)
                if not file_path.is_file():
                    raise FileNotFoundError(f"Feedback file not found: {file_path}")
                if file_path.stat().st_size > 1_000_000:
                    raise ValueError(f"Feedback file exceeds the 1 MB limit: {file_path}")
                content = file_path.read_text(encoding="utf-8-sig")
                self._parse_content(content)
            else:
                # 直接解析文本
                self._parse_content(input_item)

        return self.feedback

    def _is_file_reference(self, text):
        """判断是否是文件引用"""
        return text.strip().startswith('@')

    def _resolve_file_path(self, reference, base_dir):
        """Resolve a referenced feedback file without allowing directory escape."""
        root = Path(base_dir).expanduser().resolve()
        referenced = Path(reference.strip()[1:]).expanduser()
        candidate = referenced if referenced.is_absolute() else root / referenced
        candidate = candidate.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("Feedback file references must stay inside the skill directory") from exc
        return candidate

    def _parse_content(self, content):
        """
        从内容中提取信息
        """
        # 1. 提取问题
        issues = self._extract_issues(content)
        self.feedback["issues"].extend(issues)

        # 2. 提取使用案例
        examples = self._extract_examples(content)
        self.feedback["examples"].extend(examples)

        # 3. 提取好的做法
        good = self._extract_good_practices(content)
        self.feedback["good"].extend(good)

        # 4. 提取建议
        suggestions = self._extract_suggestions(content)
        self.feedback["suggestions"].extend(suggestions)

    def _extract_issues(self, content):
        """
        提取问题描述

        识别模式：
        - "问题："、"Problem:"
        - "bug"、"错误"
        - "不应该"、"shouldn't"
        - "太..."、"too..."
        - "缺少"、"missing"
        """
        issues = []
        label_pattern = r"(?:问题|bug|错误|issue|problem|好的|保留|正确|优点|good|keep|correct|建议|希望|应该|可以改成|改进|suggestion)"
        explicit_pattern = re.compile(r"^(?:问题|bug|错误|issue|problem)[:：]\s*(.+)$", re.IGNORECASE)
        non_issue_label = re.compile(r"^(?:好的|保留|正确|优点|good|keep|correct|建议|希望|应该|可以改成|改进|suggestion)[:：]", re.IGNORECASE)
        broad_pattern = re.compile(r"(?:不应该|太|缺少|没有|too\b|missing\b|shouldn't\b)", re.IGNORECASE)

        for raw_line in content.splitlines():
            segments = re.split(rf"(?:(?<=[。！？.!?])\s*|\s+)(?={label_pattern}[:：])", raw_line)
            for segment in segments:
                line = re.sub(r"^\s*[-*]\s*", "", segment).strip()
                explicit = explicit_pattern.match(line)
                if explicit:
                    description = explicit.group(1).strip()
                    original_type = "explicit"
                elif not non_issue_label.match(line) and broad_pattern.search(line):
                    description = line
                    original_type = "inferred"
                else:
                    continue

                if len(description) > 3:
                    issues.append({
                        "description": description,
                        "type": self._classify_issue_type(description),
                        "source": "user_feedback",
                        "original_type": original_type,
                    })

        return issues

    def _classify_issue_type(self, description):
        """
        自动分类问题类型
        """
        desc_lower = description.lower()

        # 输出相关
        if any(word in desc_lower for word in ["输出", "结果", "报告", "格式"]):
            if any(word in desc_lower for word in ["太长", "啰嗦", "太多", "冗余"]):
                return "output_too_verbose"
            elif any(word in desc_lower for word in ["太短", "不够", "太简单"]):
                return "output_too_brief"
            else:
                return "output_format"

        # 功能相关
        if any(word in desc_lower for word in ["没有", "缺少", "不支持", "希望有", "需要"]):
            return "missing_feature"

        # 触发相关
        if any(word in desc_lower for word in ["触发", "不该", "误", "没反应", "没触发"]):
            if any(word in desc_lower for word in ["不该", "误触发", "错误地"]):
                return "trigger_false_positive"
            elif any(word in desc_lower for word in ["没反应", "没触发", "不工作"]):
                return "trigger_false_negative"
            return "trigger_accuracy"

        # 性能相关
        if any(word in desc_lower for word in ["太慢", "卡", "时间长", "性能"]):
            return "performance"

        # 边界相关
        if any(word in desc_lower for word in ["不清楚", "搞混", "什么时候用", "边界"]):
            return "boundary_unclear"

        return "general"

    def _extract_examples(self, content):
        """
        提取使用案例

        识别模式：
        - "案例"、"Example"
        - "我说...结果..."
        - "输入...输出..."
        - "User:...Agent:..."
        """
        examples = []

        # 对话格式
        conversation_pattern = r"(?:User|用户)[:：]\s*(.+?)\s*(?:Agent|助手|AI)[:：]\s*(.+?)(?=(?:User|用户):|$)"
        matches = re.findall(conversation_pattern, content, re.DOTALL | re.IGNORECASE)
        for user_input, agent_output in matches:
            examples.append({
                "type": "conversation",
                "input": user_input.strip(),
                "output": agent_output.strip()
            })

        # 输入输出格式
        io_pattern = r"输入[:：]\s*(.+?)\s*输出[:：]\s*(.+?)(?=输入|$)"
        matches = re.findall(io_pattern, content, re.DOTALL)
        for input_text, output_text in matches:
            examples.append({
                "type": "input_output",
                "input": input_text.strip(),
                "output": output_text.strip()
            })

        # 期望格式
        expect_pattern = r"期望[:：]\s*(.+?)(?=实际|$)"
        matches = re.findall(expect_pattern, content, re.DOTALL)
        for expected in matches:
            examples.append({
                "type": "expectation",
                "expected": expected.strip()
            })

        return examples

    def _extract_good_practices(self, content):
        """
        提取好的做法（应该保留）

        识别模式：
        - "好的"、"Good"
        - "保留"、"keep"
        - "正确"、"correct"
        """
        good = []

        patterns = [
            r"好的[:：]\s*(.+)",
            r"保留[:：]\s*(.+)",
            r"正确[:：]\s*(.+)",
            r"优点[:：]\s*(.+)",
            r"good[:：]\s*(.+)",
            r"keep[:：]\s*(.+)",
            r"correct[:：]\s*(.+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                text = match.strip() if isinstance(match, str) else match[0].strip()
                text = text.rstrip("。！？.!?").strip()
                if text and len(text) > 3:
                    good.append(text)

        return good

    def _extract_suggestions(self, content):
        """
        提取改进建议

        识别模式：
        - "建议"、"Suggestion"
        - "希望"、"want"
        - "应该"、"should"
        - "可以改成"、"could be"
        """
        suggestions = []

        patterns = [
            r"建议[:：]\s*(.+)",
            r"希望[:：]\s*(.+)",
            r"应该[:：]\s*(.+)",
            r"可以改成[:：]\s*(.+)",
            r"改进[:：]\s*(.+)",
            r"suggestion[:：]\s*(.+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                text = match.strip() if isinstance(match, str) else match[0].strip()
                if text and len(text) > 3:
                    suggestions.append(text)

        return suggestions

    def summarize(self):
        """生成反馈摘要"""
        return {
            "total_issues": len(self.feedback["issues"]),
            "total_examples": len(self.feedback["examples"]),
            "total_good": len(self.feedback["good"]),
            "total_suggestions": len(self.feedback["suggestions"]),
            "issue_types": self._count_issue_types()
        }

    def _count_issue_types(self):
        """统计问题类型"""
        type_count = {}
        for issue in self.feedback["issues"]:
            issue_type = issue.get("type", "general")
            type_count[issue_type] = type_count.get(issue_type, 0) + 1
        return type_count


if __name__ == "__main__":
    # 测试
    parser = FeedbackParser()

    test_feedback = """
    我在使用这个 skill 时发现几个问题：

    问题：输出太啰嗦了，每个问题都解释很长

    缺少 SQL 注入检测功能

    好的：逻辑问题检测很准确

    建议：提供简洁模式和详细模式

    User: 解释这段代码
    Agent: [触发了审查 skill]

    问题：这里不应该触发
    """

    result = parser.parse(test_feedback)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n摘要:")
    print(json.dumps(parser.summarize(), indent=2, ensure_ascii=False))
