"""
DeepSeek API 集成模块

功能：
1. 调用 DeepSeek API 对复盘报告进行智能解读
2. 提供开关控制（可选功能）
3. 错误处理（API 失败时降级）

作者：Claude
日期：2025-10-21
"""

import requests
import json
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DeepSeekAnalyzer:
    """DeepSeek AI 分析器"""

    def __init__(self, api_key: Optional[str] = None, config: dict = None):
        """
        初始化分析器

        Args:
            api_key: DeepSeek API Key（可选）
            config: 配置字典
        """
        self.api_key = api_key
        self.config = config or {}
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"
        self.enabled = bool(api_key)

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.enabled and bool(self.api_key)

    def analyze_report(
        self,
        report_data: Dict,
        language: str = "zh"
    ) -> Dict[str, str]:
        """
        分析复盘报告

        Args:
            report_data: 报告数据（来自 renderer.render_json）
            language: 语言 'zh' 或 'en'

        Returns:
            {
                'summary': '一句话总结',
                'key_points': '3-5个关键点',
                'trading_advice': '具体交易建议',
                'risk_warning': '风险提示'
            }
        """
        if not self.is_enabled():
            logger.warning("DeepSeek 未启用，返回默认分析")
            return self._get_default_analysis(report_data)

        try:
            # 构造提示词
            prompt = self._build_prompt(report_data, language)

            # 调用 API
            response = self._call_api(prompt)

            # 解析响应
            analysis = self._parse_response(response)

            logger.info("DeepSeek 分析成功")
            return analysis

        except Exception as e:
            logger.error(f"DeepSeek 分析失败: {e}")
            return self._get_default_analysis(report_data)

    def _build_prompt(self, report_data: Dict, language: str) -> str:
        """构造提示词"""
        # 提取关键数据
        scores = report_data.get('scores', {})
        composite = scores.get('composite', {})
        allocation = report_data.get('allocation', {})
        analysis = report_data.get('analysis', {})

        composite_score = composite.get('total_score', 0)
        market_level = composite.get('level', '未知')
        position = composite.get('position', 50)

        bullish = analysis.get('bullish_factors', [])
        bearish = analysis.get('bearish_factors', [])

        # 构造提示词
        if language == "zh":
            prompt = f"""你是一位资深的A股市场分析师。请基于以下量化分析数据，给出专业的市场解读和交易建议。

【市场评分】
- 综合得分: {composite_score:.1f} / 100
- 市场状态: {market_level}
- 建议仓位: {position}%

【四维度得分】
- 宏观: {composite.get('breakdown', {}).get('macro', 0):.1f}
- 流动性: {composite.get('breakdown', {}).get('liquidity', 0):.1f}
- 风险偏好: {composite.get('breakdown', {}).get('riskon', 0):.1f}
- 动量: {composite.get('breakdown', {}).get('momentum', 0):.1f}

【利好因素】
{self._format_factors(bullish)}

【利空因素】
{self._format_factors(bearish)}

【配置建议】
- 风格: {allocation.get('style', {}).get('style', '未知')}
- 权益仓位: {allocation.get('position', {}).get('equity_position', 0)}%

请提供以下内容（使用JSON格式输出）：
{{
    "summary": "一句话总结当前市场状态（20字以内）",
    "key_points": "3-5个关键观察点，用换行符分隔，每条用「-」开头",
    "trading_advice": "具体的交易建议，包括仓位操作、板块选择等，用换行符分隔",
    "risk_warning": "主要风险点和注意事项，用换行符分隔"
}}

要求：
1. 专业、客观、简洁
2. 避免模棱两可的表述
3. 给出可执行的建议
4. 每条建议不超过50字
"""
        else:
            prompt = f"""You are a senior A-share market analyst. Based on the following quantitative analysis data, provide professional market interpretation and trading advice.

【Market Score】
- Composite Score: {composite_score:.1f} / 100
- Market Status: {market_level}
- Recommended Position: {position}%

【Four Dimensions】
- Macro: {composite.get('breakdown', {}).get('macro', 0):.1f}
- Liquidity: {composite.get('breakdown', {}).get('liquidity', 0):.1f}
- Risk Appetite: {composite.get('breakdown', {}).get('riskon', 0):.1f}
- Momentum: {composite.get('breakdown', {}).get('momentum', 0):.1f}

【Bullish Factors】
{self._format_factors(bullish)}

【Bearish Factors】
{self._format_factors(bearish)}

Please provide analysis in JSON format:
{{
    "summary": "One-sentence market summary",
    "key_points": "3-5 key observations, separated by newlines, each starting with \"-\"",
    "trading_advice": "Specific trading recommendations",
    "risk_warning": "Main risk points and precautions"
}}
"""

        return prompt

    def _format_factors(self, factors: list) -> str:
        """格式化因素列表"""
        if not factors:
            return "无"

        lines = []
        for i, factor in enumerate(factors, 1):
            title = factor.get('title', '')
            desc = factor.get('description', '')
            lines.append(f"{i}. {title}: {desc}")

        return "\n".join(lines)

    def _call_api(self, prompt: str) -> dict:
        """调用 DeepSeek API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的A股市场分析师，擅长解读量化数据并给出实用建议。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }

        logger.info("正在调用 DeepSeek API...")

        response = requests.post(
            self.base_url,
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()
        return response.json()

    def _parse_response(self, response: dict) -> Dict[str, str]:
        """解析 API 响应"""
        try:
            content = response['choices'][0]['message']['content']

            # 尝试解析 JSON
            # 去除可能的 markdown 代码块标记
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]

            content = content.strip()

            analysis = json.loads(content)

            return {
                'summary': analysis.get('summary', ''),
                'key_points': analysis.get('key_points', ''),
                'trading_advice': analysis.get('trading_advice', ''),
                'risk_warning': analysis.get('risk_warning', '')
            }

        except Exception as e:
            logger.error(f"解析 DeepSeek 响应失败: {e}")
            logger.debug(f"原始响应: {response}")

            # 返回原始内容
            try:
                content = response['choices'][0]['message']['content']
                return {
                    'summary': '解析失败',
                    'key_points': content[:500],
                    'trading_advice': '',
                    'risk_warning': ''
                }
            except:
                return self._get_empty_analysis()

    def _get_default_analysis(self, report_data: Dict) -> Dict[str, str]:
        """获取默认分析（当 API 不可用时）"""
        scores = report_data.get('scores', {})
        composite = scores.get('composite', {})

        score = composite.get('total_score', 0)
        level = composite.get('level', '未知')
        position = composite.get('position', 50)

        if score >= 70:
            summary = "市场偏强，建议积极参与"
        elif score >= 60:
            summary = "市场中性偏多，谨慎乐观"
        elif score >= 50:
            summary = "市场中性，保持观望"
        elif score >= 40:
            summary = "市场偏弱，控制风险"
        else:
            summary = "市场疲弱，防御为主"

        return {
            'summary': summary,
            'key_points': f"- 综合得分: {score:.1f}分\n- 市场状态: {level}\n- 建议仓位: {position}%",
            'trading_advice': "根据个人风险偏好调整仓位，关注行业轮动机会",
            'risk_warning': "市场存在不确定性，注意控制仓位和止损"
        }

    def _get_empty_analysis(self) -> Dict[str, str]:
        """获取空分析"""
        return {
            'summary': '',
            'key_points': '',
            'trading_advice': '',
            'risk_warning': ''
        }


if __name__ == '__main__':
    # 测试代码
    import yaml

    # 模拟报告数据
    mock_report = {
        'meta': {
            'date': '2025-10-21',
            'version': '1.0.0'
        },
        'scores': {
            'composite': {
                'total_score': 62.1,
                'position': 65,
                'level': '中性偏多',
                'breakdown': {
                    'macro': 61.0,
                    'liquidity': 67.2,
                    'riskon': 54.5,
                    'momentum': 62.0
                }
            }
        },
        'allocation': {
            'position': {
                'equity_position': 65
            },
            'style': {
                'style': 'balanced'
            }
        },
        'analysis': {
            'bullish_factors': [
                {'title': '宏观面偏暖', 'description': '宏观维度得分61.0'},
                {'title': '流动性充裕', 'description': '流动性维度得分67.2'}
            ],
            'bearish_factors': [
                {'title': '部分行业拥挤', 'description': '医药、消费等行业弱势+高拥挤'}
            ]
        }
    }

    print("=" * 80)
    print("DeepSeek 集成模块测试")
    print("=" * 80)

    # 测试无 API Key（默认分析）
    print("\n【测试1: 无 API Key - 使用默认分析】")
    analyzer = DeepSeekAnalyzer(api_key=None)
    result = analyzer.analyze_report(mock_report)

    print(f"\n一句话总结: {result['summary']}")
    print(f"\n关键点:\n{result['key_points']}")
    print(f"\n交易建议:\n{result['trading_advice']}")
    print(f"\n风险提示:\n{result['risk_warning']}")

    # 测试有 API Key（需要真实的 Key）
    print("\n" + "=" * 80)
    print("【测试2: 有 API Key】")
    print("提示: 需要设置环境变量 DEEPSEEK_API_KEY 才能测试")
    print("示例: export DEEPSEEK_API_KEY='sk-xxxxxxxx'")

    import os
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if api_key:
        analyzer = DeepSeekAnalyzer(api_key=api_key)
        print(f"DeepSeek 启用状态: {analyzer.is_enabled()}")

        try:
            result = analyzer.analyze_report(mock_report)
            print(f"\n一句话总结: {result['summary']}")
            print(f"\n关键点:\n{result['key_points']}")
            print(f"\n交易建议:\n{result['trading_advice']}")
            print(f"\n风险提示:\n{result['risk_warning']}")
        except Exception as e:
            print(f"\n❌ API 调用失败: {e}")
    else:
        print("未设置 DEEPSEEK_API_KEY，跳过 API 测试")

    print("\n" + "=" * 80)
    print("✅ DeepSeek 集成模块测试完成！")
    print("=" * 80)
