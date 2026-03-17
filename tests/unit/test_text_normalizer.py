"""文本规范化服务的单元测试。

覆盖 ``normalize_text`` 和 ``normalize_test_case`` 的核心场景：
- 常见英文动作词替换
- snake_case / camelCase / ALL_CAPS 标识符保护
- 反引号包裹内容保护
- URL 保护
- 结构性术语替换
- 中英文混排内容不被重复处理
- TestCase 对象整体规范化
"""

from __future__ import annotations

import pytest

from app.domain.case_models import TestCase
from app.services.text_normalizer import normalize_test_case, normalize_text


class TestNormalizeCommonEnglishActions:
    """测试常见英文动作词的中文替换。"""

    def test_click(self) -> None:
        result = normalize_text("Click the button")
        assert "点击" in result
        assert "Click" not in result

    def test_select(self) -> None:
        result = normalize_text("Select an option from the dropdown")
        assert "选择" in result

    def test_input(self) -> None:
        result = normalize_text("Input the username")
        assert "输入" in result

    def test_enter(self) -> None:
        result = normalize_text("Enter the password")
        assert "输入" in result

    def test_verify(self) -> None:
        result = normalize_text("Verify the result")
        assert "验证" in result

    def test_check(self) -> None:
        result = normalize_text("Check the status")
        assert "检查" in result

    def test_confirm(self) -> None:
        result = normalize_text("Confirm the dialog")
        assert "确认" in result

    def test_create(self) -> None:
        result = normalize_text("Create a new record")
        assert "创建" in result

    def test_submit(self) -> None:
        result = normalize_text("Submit the form")
        assert "提交" in result

    def test_delete(self) -> None:
        result = normalize_text("Delete the item")
        assert "删除" in result

    def test_open(self) -> None:
        result = normalize_text("Open the settings page")
        assert "打开" in result

    def test_close(self) -> None:
        result = normalize_text("Close the modal")
        assert "关闭" in result

    def test_save(self) -> None:
        result = normalize_text("Save the changes")
        assert "保存" in result

    def test_cancel(self) -> None:
        result = normalize_text("Cancel the operation")
        assert "取消" in result

    def test_edit(self) -> None:
        result = normalize_text("Edit the profile")
        assert "编辑" in result

    def test_update(self) -> None:
        result = normalize_text("Update the settings")
        assert "更新" in result

    def test_search(self) -> None:
        result = normalize_text("Search for users")
        assert "搜索" in result

    def test_login(self) -> None:
        result = normalize_text("Login to the system")
        assert "登录" in result

    def test_logout(self) -> None:
        result = normalize_text("Logout from the system")
        assert "登出" in result

    def test_upload(self) -> None:
        result = normalize_text("Upload the file")
        assert "上传" in result

    def test_download(self) -> None:
        result = normalize_text("Download the report")
        assert "下载" in result

    def test_navigate(self) -> None:
        result = normalize_text("Navigate to the home page")
        assert "导航" in result

    def test_refresh(self) -> None:
        result = normalize_text("Refresh the page")
        assert "刷新" in result


class TestPreserveSnakeCase:
    """测试 snake_case 标识符的保护。"""

    def test_preserve_campaign_id(self) -> None:
        result = normalize_text("Check campaign_id field")
        assert "campaign_id" in result
        assert "检查" in result

    def test_preserve_user_name(self) -> None:
        result = normalize_text("Verify user_name is not empty")
        assert "user_name" in result

    def test_preserve_order_status(self) -> None:
        result = normalize_text("Check order_status value")
        assert "order_status" in result


class TestPreserveCamelCase:
    """测试 camelCase 标识符的保护。"""

    def test_preserve_handleClick(self) -> None:
        result = normalize_text("Verify handleClick function")
        assert "handleClick" in result

    def test_preserve_getUserInfo(self) -> None:
        result = normalize_text("Check getUserInfo response")
        assert "getUserInfo" in result

    def test_preserve_isActive(self) -> None:
        result = normalize_text("Verify isActive flag")
        assert "isActive" in result


class TestPreserveAllCaps:
    """测试 ALL_CAPS 缩写词的保护。"""

    def test_preserve_api(self) -> None:
        result = normalize_text("Call API endpoint")
        assert "API" in result

    def test_preserve_url(self) -> None:
        result = normalize_text("Check URL format")
        assert "URL" in result

    def test_preserve_json(self) -> None:
        result = normalize_text("Verify JSON response")
        assert "JSON" in result

    def test_preserve_id(self) -> None:
        result = normalize_text("Check ID value")
        assert "ID" in result

    def test_preserve_cta(self) -> None:
        result = normalize_text("Click CTA button")
        assert "CTA" in result


class TestPreserveBacktickContent:
    """测试反引号包裹内容的保护。"""

    def test_preserve_backtick_button(self) -> None:
        result = normalize_text("Click `Create campaign` button")
        assert "`Create campaign`" in result

    def test_preserve_backtick_field(self) -> None:
        result = normalize_text("Check `user_name` field value")
        assert "`user_name`" in result

    def test_preserve_backtick_code(self) -> None:
        result = normalize_text("Verify `response.status` equals 200")
        assert "`response.status`" in result


class TestMixedChineseEnglish:
    """测试已包含中文的文本不被重复处理。"""

    def test_already_chinese(self) -> None:
        text = "点击按钮并验证结果"
        result = normalize_text(text)
        assert result == text

    def test_mixed_preserved(self) -> None:
        text = "点击 `Submit` 按钮"
        result = normalize_text(text)
        assert "`Submit`" in result
        assert "点击" in result

    def test_empty_string(self) -> None:
        assert normalize_text("") == ""

    def test_none_like_empty(self) -> None:
        assert normalize_text("   ") == "   "


class TestNormalizeStructuralTerms:
    """测试结构性术语的中文替换。"""

    def test_preconditions(self) -> None:
        result = normalize_text("Preconditions:")
        assert "前置条件" in result

    def test_precondition_singular(self) -> None:
        result = normalize_text("Precondition: user logged in")
        assert "前置条件" in result

    def test_steps(self) -> None:
        result = normalize_text("Steps to reproduce")
        assert "步骤" in result

    def test_expected_results(self) -> None:
        result = normalize_text("Expected Results")
        assert "预期结果" in result

    def test_main_branch(self) -> None:
        result = normalize_text("Main branch testing")
        assert "主分支" in result

    def test_edge_case(self) -> None:
        result = normalize_text("Edge case scenario")
        assert "边界场景" in result

    def test_exception_branch(self) -> None:
        result = normalize_text("Exception branch handling")
        assert "异常分支" in result

    def test_error_branch(self) -> None:
        result = normalize_text("Error branch flow")
        assert "异常分支" in result


class TestNormalizeTestCase:
    """测试 TestCase 对象整体规范化。"""

    def test_normalize_test_case_fields(self) -> None:
        case = TestCase(
            id="TC-001",
            title="Click the Submit button",
            preconditions=["Open the login page", "Enter valid credentials"],
            steps=["Click the Submit button", "Verify the dashboard loads"],
            expected_results=["User is redirected to dashboard"],
            priority="P1",
            category="functional",
            checkpoint_id="CP-abc123",
        )

        normalized = normalize_test_case(case)

        # title 应被规范化
        assert "点击" in normalized.title
        # steps 应被规范化
        assert "点击" in normalized.steps[0]
        assert "验证" in normalized.steps[1]
        # expected_results 应被规范化
        # preconditions 应被规范化
        assert "打开" in normalized.preconditions[0]
        assert "输入" in normalized.preconditions[1]
        # id 不应被修改
        assert normalized.id == "TC-001"
        # priority 不应被修改
        assert normalized.priority == "P1"
        # checkpoint_id 不应被修改
        assert normalized.checkpoint_id == "CP-abc123"


class TestPreserveURL:
    """测试 URL 的保护。"""

    def test_preserve_http_url(self) -> None:
        result = normalize_text("Open https://example.com/login page")
        assert "https://example.com/login" in result
        assert "打开" in result

    def test_preserve_url_with_params(self) -> None:
        result = normalize_text("Navigate to https://api.example.com/v1/users?status=active")
        assert "https://api.example.com/v1/users?status=active" in result


class TestPreserveJSONFieldNames:
    """测试 JSON 风格的字段引用保护。"""

    def test_preserve_dot_path(self) -> None:
        result = normalize_text("Check response.data.items count")
        assert "response.data.items" in result
        assert "检查" in result

    def test_preserve_nested_field(self) -> None:
        result = normalize_text("Verify user.profile.name value")
        assert "user.profile.name" in result
