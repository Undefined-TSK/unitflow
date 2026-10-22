"""ingest 测试：7 格式解析 / ZIP 炸弹 / 安全检查 / 角色归一（全本地，零 API）。"""
import io
import zipfile

import pytest
from openpyxl import Workbook
from pptx import Presentation
from docx import Document as DocxDoc

from pypedia import ingest
from pypedia.config import settings


@pytest.fixture()
def tmp_files(tmp_path):
    """构造各格式测试文件。"""
    files = {}

    # Markdown / TXT
    p = tmp_path / "a.md"
    p.write_text("# 标题\n\nPython 装饰器内容。", encoding="utf-8")
    files["md"] = p
    p = tmp_path / "a.txt"
    p.write_text("纯文本内容 asyncio", encoding="utf-8")
    files["txt"] = p

    # HTML（含 script/style 噪声）
    p = tmp_path / "a.html"
    p.write_text(
        "<html><head><style>body{color:red}</style></head>"
        "<body><script>alert(1)</script><p>正文 列表推导式</p></body></html>",
        encoding="utf-8")
    files["html"] = p

    # DOCX
    p = tmp_path / "a.docx"
    d = DocxDoc()
    d.add_heading("DOCX 标题", 0)
    d.add_paragraph("DOCX 正文：生成器")
    d.save(str(p))
    files["docx"] = p

    # PPTX
    p = tmp_path / "a.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "PPTX 标题"
    prs.save(str(p))
    files["pptx"] = p

    # XLSX
    p = tmp_path / "a.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(["名称", "说明"])
    ws.append(["列表", "有序序列"])
    wb.save(str(p))
    files["xlsx"] = p

    # EPUB（用 ebooklib 自身构造，保证结构合法）
    import ebooklib
    from ebooklib import epub

    p = tmp_path / "a.epub"
    book = epub.EpubBook()
    book.set_identifier("test")
    book.set_title("EPUB 标题")
    book.set_language("zh")
    ch = epub.EpubHtml(title="第一章", file_name="ch1.xhtml", lang="zh")
    ch.content = "<h1>EPUB 标题</h1><p>EPUB 正文 迭代器</p>"
    book.add_item(ch)
    book.toc = [epub.Link("ch1.xhtml", "第一章", "ch1")]
    book.spine = [ch]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(p), book)
    files["epub"] = p

    # ZIP 炸弹（1MB 零压缩到 >100:1）
    p = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sheet.xml", "0" * (10 * 1024 * 1024))
    files["bomb"] = p
    return files


class TestParseFile:
    def test_markdown(self, tmp_files):
        assert "装饰器" in ingest.parse_file(str(tmp_files["md"]))

    def test_txt(self, tmp_files):
        assert "asyncio" in ingest.parse_file(str(tmp_files["txt"]))

    def test_html_strips_script_style(self, tmp_files):
        text = ingest.parse_file(str(tmp_files["html"]))
        assert "列表推导式" in text
        assert "alert" not in text
        assert "color:red" not in text

    def test_docx(self, tmp_files):
        text = ingest.parse_file(str(tmp_files["docx"]))
        assert "DOCX" in text and "生成器" in text

    def test_pptx(self, tmp_files):
        text = ingest.parse_file(str(tmp_files["pptx"]))
        assert "PPTX" in text

    def test_xlsx(self, tmp_files):
        text = ingest.parse_file(str(tmp_files["xlsx"]))
        assert "列表" in text and "有序序列" in text

    def test_epub(self, tmp_files):
        text = ingest.parse_file(str(tmp_files["epub"]))
        assert "EPUB" in text

    def test_unsupported_ext(self, tmp_files):
        p = tmp_files["md"].with_suffix(".bin")
        p.write_bytes(b"\x00\x01")
        assert ingest.parse_file(str(p)) == "[不支持的格式]"

    def test_corrupt_returns_message(self, tmp_files):
        p = tmp_files["md"].with_suffix(".pdf")
        p.write_bytes(b"not a pdf at all")
        out = ingest.parse_file(str(p))
        assert out.startswith("[解析失败]")


class TestZipSafety:
    def test_bomb_rejected(self, tmp_files):
        with pytest.raises(ValueError, match="解压炸弹"):
            ingest._check_zip_safe(str(tmp_files["bomb"]))

    def test_normal_zip_passes(self, tmp_files):
        ingest._check_zip_safe(str(tmp_files["epub"]))  # 不抛即通过

    def test_check_file_safe_bomb(self, tmp_files):
        reason = ingest.check_file_safe(str(tmp_files["bomb"]))
        assert "炸弹" in reason

    def test_check_file_safe_oversize(self, tmp_files, monkeypatch):
        monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0.00001)  # ~10 字节，必超
        reason = ingest.check_file_safe(str(tmp_files["md"]))
        assert "超过上限" in reason

    def test_check_file_safe_ok(self, tmp_files):
        assert ingest.check_file_safe(str(tmp_files["md"])) == ""


class TestNormRole:
    @pytest.mark.parametrize("raw,expect", [
        ("main", "main"), ("PRIMARY", "main"), ("主要", "main"),
        ("supplement_a", "supplement_a"), ("补充A", "supplement_a"), ("github", "supplement_a"),
        ("supplement_b", "supplement_b"), ("", "supplement_b"),
        ("garbage", "supplement_b"), (None, "supplement_b"),
    ])
    def test_mapping(self, raw, expect):
        assert ingest._norm_role(raw) == expect


class TestHtmlToText:
    def test_bytes_input(self):
        out = ingest.html_to_text("<html><body><p>hello 世界</p></body></html>".encode())
        assert "hello" in out and "世界" in out

    def test_empty_input_no_crash(self):
        assert ingest.html_to_text("") in ("", None) or isinstance(ingest.html_to_text(""), str)
