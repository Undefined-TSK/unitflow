"""自进化数据层测试：数据文件损坏时不得静默丢数据。

背景（真实缺陷）：`_read()` 解析失败时静默返回 []，随后下一次 `_write()`
会把损坏文件整个覆盖 —— 用户沉淀的技能/反思永久丢失且毫无痕迹。
现改为：留痕日志 + 把损坏原件改名隔离。
"""
import json

import pytest


@pytest.fixture
def clean_dir():
    """清掉可能残留的损坏文件，避免用例间互相干扰。"""
    from pypedia.evolution.voyager import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for pat in ("skills*.json", "reflections*.json"):
        for f in DATA_DIR.glob(pat):
            f.unlink()
    return DATA_DIR


class TestCorruptFileQuarantine:
    def test_skills_corrupt_quarantined(self, clean_dir):
        from pypedia.evolution.voyager import SkillLibrary

        p = clean_dir / "skills.json"
        p.write_text("{ this is not json", encoding="utf-8")

        lib = SkillLibrary()
        assert lib.list_skills() == []  # 不崩，降级为空
        # 关键：原件被改名保留，而不是被下一次写入覆盖
        assert list(clean_dir.glob("skills.corrupt-*.json")), "损坏原件应被隔离保留"

    def test_reflections_corrupt_quarantined(self, clean_dir):
        from pypedia.evolution.reflexion import ReflectionLog

        p = clean_dir / "reflections.json"
        p.write_text("[unterminated", encoding="utf-8")

        log = ReflectionLog()
        assert log.recent(5) == []
        assert list(clean_dir.glob("reflections.corrupt-*.json")), "损坏原件应被隔离保留"

    def test_normal_write_still_works(self, clean_dir):
        """隔离逻辑不能影响正常读写路径。"""
        from pypedia.evolution.voyager import SkillLibrary

        lib = SkillLibrary()
        assert lib.add_skill("测试技能", "当测试时", "执行断言") is True
        assert lib.add_skill("测试技能", "当测试时", "执行断言") is False  # 同名覆盖
        data = json.loads((clean_dir / "skills.json").read_text(encoding="utf-8"))
        assert [d["name"] for d in data] == ["测试技能"]
        assert not list(clean_dir.glob("*.corrupt-*.json"))  # 正常路径不产生隔离文件
