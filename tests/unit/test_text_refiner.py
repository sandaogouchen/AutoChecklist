"""单元测试：text_normalizer 文本精炼功能（refine_text / refine_test_case）。"""

from __future__ import annotations

import pytest

from app.services.text_normalizer import refine_text, _merge_redundant_steps


# ---------------------------------------------------------------------------
# refine_text 测试
# ---------------------------------------------------------------------------

class TestRefineText:
    """refine_text 基本功能。"""

    # ---- 中文前缀去除 ----

    def test_zh_prefix_removal_verify(self):
        result = refine_text("验证用户能够正常登录", text_type="step", language="zh-CN")
        assert not result.startswith("验证")

    def test_zh_prefix_removal_check(self):
        result = refine_text("检查页面是否显示正确", text_type="step", language="zh-CN")
        assert not result.startswith("检查")

    def test_zh_prefix_removal_confirm(self):
        result = refine_text("确认订单状态已更新", text_type="step", language="zh-CN")
        assert not result.startswith("确认")

    # ---- 中文后缀去除 ----

    def test_zh_suffix_removal(self):
        result = refine_text("登录功能是否正常", text_type="step", language="zh-CN")
        assert not result.endswith("是否正常")

    # ---- 英文前缀去除 ----

    def test_en_prefix_removal_verify(self):
        result = refine_text("Verify that the button works", text_type="step", language="en")
        assert not result.startswith("Verify that")

    def test_en_prefix_removal_ensure(self):
        result = refine_text("Ensure the page loads", text_type="step", language="en")
        assert not result.startswith("Ensure")

    # ---- 英文后缀去除 ----

    def test_en_suffix_removal(self):
        result = refine_text("The system works as expected", text_type="step", language="en")
        assert not result.endswith("as expected")

    # ---- 反引号内容保护 ----

    def test_backtick_content_preserved(self):
        text = "验证 `submit_button` 可以点击"
        result = refine_text(text, text_type="step", language="zh-CN")
        assert "`submit_button`" in result

    # ---- URL 保护 ----

    def test_url_preserved(self):
        text = "导航到 https://example.com/login 页面"
        result = refine_text(text, text_type="step", language="zh-CN")
        assert "https://example.com/login" in result

    # ---- 长度约束 ----

    def test_length_constraint(self):
        long_text = "这是一个" * 100
        result = refine_text(long_text, text_type="step", language="zh-CN")
        assert len(result) <= 120  # zh step limit

    # ---- 空字符串 ----

    def test_empty_string(self):
        assert refine_text("", text_type="step", language="zh-CN") == ""

    # ---- 已经简洁的文本不变 ----

    def test_clean_text_unchanged(self):
        text = "点击登录按钮"
        result = refine_text(text, text_type="step", language="zh-CN")
        assert result == text


# ---------------------------------------------------------------------------
# _merge_redundant_steps 测试
# ---------------------------------------------------------------------------

class TestMergeRedundantSteps:
    """冗余步骤合并。"""

    def test_duplicate_steps_merged(self):
        steps = ["打开浏览器", "打开浏览器", "输入用户名"]
        result = _merge_redundant_steps(steps, language="zh-CN")
        assert result.count("打开浏览器") == 1

    def test_similar_steps_merged(self):
        steps = ["打开浏览器并等待加载", "打开浏览器并等待页面加载", "输入用户名"]
        result = _merge_redundant_steps(steps, language="zh-CN")
        # 高相似度的步骤应被合并
        assert len(result) < len(steps)

    def test_different_steps_kept(self):
        steps = ["打开浏览器", "输入用户名", "点击登录"]
        result = _merge_redundant_steps(steps, language="zh-CN")
        assert len(result) == 3
