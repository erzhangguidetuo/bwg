"""文档解析：把 PDF / DOCX / Markdown / TXT 统一解析为带元数据的文本块。

每个返回元素是一个 dict：
    {"text": 文本内容, "metadata": {"source": 文件名, "page": 页码或 None}}

统一格式的好处：后续分块、入库环节不关心原始文件类型。
"""
from pathlib import Path


def _load_pdf(path: Path) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    results = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            results.append(
                {"text": text, "metadata": {"source": path.name, "page": i + 1}}
            )
    return results


def _load_docx(path: Path) -> list[dict]:
    import docx

    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return [{"text": "\n".join(paragraphs), "metadata": {"source": path.name, "page": None}}]


def _load_text(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [{"text": text, "metadata": {"source": path.name, "page": None}}]


# 扩展名 -> 解析函数。新增格式时在这里注册即可。
_LOADERS = {
    ".pdf": _load_pdf,
    ".docx": _load_docx,
    ".md": _load_text,
    ".markdown": _load_text,
    ".txt": _load_text,
}


def load_file(path: Path) -> list[dict]:
    """按扩展名分派解析，不支持的格式抛出明确错误。"""
    ext = path.suffix.lower()
    if ext not in _LOADERS:
        raise ValueError(f"不支持的文件格式: {ext}（支持: {sorted(_LOADERS)}）")
    return _LOADERS[ext](path)


def load_directory(docs_dir: Path) -> list[dict]:
    """递归加载目录下所有受支持的文档。"""
    all_docs = []
    for path in sorted(docs_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in _LOADERS:
            docs = load_file(path)
            print(f"  已解析 {path.name}: {len(docs)} 个文本单元")
            all_docs.extend(docs)
    return all_docs
