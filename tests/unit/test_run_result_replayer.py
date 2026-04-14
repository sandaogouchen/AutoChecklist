from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.services.run_result_replayer import (
    replay_delivery_from_run_result,
    replay_delivery_from_testcase_json,
)


def test_replay_delivery_from_run_result_filters_reference_cases_and_rerenders(
    tmp_path: Path,
) -> None:
    fixture_dir = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "run_result_replay"
    )
    work_dir = tmp_path / "fixture-run"
    work_dir.mkdir()

    for name in ("run_result.json", "checkpoints.json"):
        (work_dir / name).write_text(
            (fixture_dir / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    result = replay_delivery_from_run_result(work_dir / "run_result.json")

    assert result.selected_case_count == 2
    assert Path(result.markdown_path).exists()
    assert Path(result.xmind_path).exists()

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "## 前置条件: 登录页" in markdown
    assert "### TC-001 正确凭证登录成功" in markdown
    assert "### TC-002 错误密码展示失败提示" in markdown
    assert "参考模版叶子一" not in markdown
    assert "参考模版叶子二" not in markdown

    with zipfile.ZipFile(result.xmind_path, "r") as zf:
        content = json.loads(zf.read("content.json"))

    root_children = content[0]["rootTopic"]["children"]["attached"]
    serialized = json.dumps(root_children, ensure_ascii=False)
    assert "正确凭证登录成功" in serialized
    assert "错误密码展示失败提示" in serialized
    assert "参考模版叶子一" not in serialized


class TestIntermediateTestcaseReplay:
    def test_replay_delivery_from_intermediate_testcase_json_generates_checklist(
        self,
        tmp_path: Path,
    ) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "output"
            / "runs"
            / "2026-04-09_17-14-38"
            / "中间态testcase.json"
        )
        if not source.exists():
            pytest.skip(f"missing intermediate testcase artifact: {source}")

        result = replay_delivery_from_testcase_json(
            source,
            output_dir=tmp_path,
            title="manual_ci_intermediate_replay",
        )

        assert result.selected_case_count == 25
        assert Path(result.markdown_path).exists()
        assert Path(result.xmind_path).exists()

        markdown = Path(result.markdown_path).read_text(encoding="utf-8")
        assert "同时开启两类白名单后成功创建CI Live Campaign" in markdown
        assert "开启Campaign层级LIVE toggle创建Manual CI" in markdown
        assert "开启LIVE后在预算策略中隐藏CBO选项" in markdown

        with zipfile.ZipFile(result.xmind_path, "r") as zf:
            content = json.loads(zf.read("content.json"))

        serialized = json.dumps(
            content[0]["rootTopic"]["children"]["attached"],
            ensure_ascii=False,
        )
        assert "同时开启两类白名单后成功创建CI Live Campaign" in serialized
        assert "Ad Group层级开启toggle后默认选中live并隐藏部分模块" in serialized
