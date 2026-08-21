"""Safe plain-text rendering for Pocketing's supported Tiptap document schema."""

from typing import Any


def _text_content(node: dict[str, Any]) -> str:
    node_type = node.get("type")
    if node_type == "text":
        text = str(node.get("text") or "")
        marks = node.get("marks") or []
        if any(mark.get("type") == "code" for mark in marks if isinstance(mark, dict)):
            if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
                text = text[1:-1]
        return text
    if node_type == "hardBreak":
        return "\n"
    return "".join(
        _text_content(child)
        for child in node.get("content") or []
        if isinstance(child, dict)
    )


def _render_list(node: dict[str, Any], depth: int) -> str:
    node_type = node.get("type")
    items = [item for item in node.get("content") or [] if isinstance(item, dict)]
    start = int((node.get("attrs") or {}).get("start") or 1)
    rendered: list[str] = []

    for index, item in enumerate(items):
        attrs = item.get("attrs") or {}
        if node_type == "orderedList":
            marker = f"{start + index}. "
        elif node_type == "taskList":
            marker = "☑ " if attrs.get("checked") else "☐ "
        else:
            marker = "• "

        direct_blocks: list[str] = []
        nested_lists: list[str] = []
        for child in item.get("content") or []:
            if not isinstance(child, dict):
                continue
            if child.get("type") in {"bulletList", "orderedList", "taskList"}:
                nested = _render_list(child, depth + 1)
                if nested:
                    nested_lists.append(nested)
            else:
                text = _render_block(child, depth)
                if text:
                    direct_blocks.append(text)

        item_text = "\n".join(direct_blocks)
        lines = item_text.splitlines() or [""]
        indent = "  " * depth
        continuation = indent + " " * len(marker)
        rendered.append(indent + marker + lines[0])
        rendered.extend(continuation + line for line in lines[1:])
        rendered.extend(nested_lists)

    return "\n".join(rendered)


def _render_block(node: dict[str, Any], depth: int = 0) -> str:
    node_type = node.get("type")
    if node_type in {"paragraph", "heading", "codeBlock"}:
        return _text_content(node)
    if node_type in {"bulletList", "orderedList", "taskList"}:
        return _render_list(node, depth)
    if node_type == "blockquote":
        quoted = "\n".join(
            _render_block(child, depth)
            for child in node.get("content") or []
            if isinstance(child, dict)
        )
        return "\n".join(f"> {line}" for line in quoted.splitlines())
    if node_type == "horizontalRule":
        return "────────"
    if node_type == "hardBreak":
        return "\n"
    return _text_content(node)


def rich_text_to_plain_text(document: dict[str, Any] | None) -> str:
    """Render one readable newline per block while retaining list semantics."""
    if not document or document.get("type") != "doc":
        return ""
    blocks = [
        _render_block(child)
        for child in document.get("content") or []
        if isinstance(child, dict)
    ]
    return "\n".join(blocks).strip()
