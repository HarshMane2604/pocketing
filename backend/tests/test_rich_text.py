import unittest

from app.schemas import NoteUpdate, validate_structured_content
from app.rich_text import rich_text_to_plain_text


class RichTextValidationTests(unittest.TestCase):
    def test_accepts_supported_tiptap_document(self) -> None:
        document = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2, "textAlign": "center"},
                    "content": [
                        {
                            "type": "text",
                            "text": "Pocketing",
                            "marks": [{"type": "bold"}],
                        }
                    ],
                },
                {
                    "type": "taskList",
                    "content": [
                        {
                            "type": "taskItem",
                            "attrs": {"checked": True},
                            "content": [{"type": "paragraph"}],
                        }
                    ],
                },
            ],
        }
        self.assertEqual(validate_structured_content(document), document)
        self.assertEqual(NoteUpdate(structured_content=document).structured_content, document)

    def test_rejects_script_nodes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported rich-text node"):
            validate_structured_content(
                {"type": "doc", "content": [{"type": "script", "text": "alert(1)"}]}
            )

    def test_rejects_unsafe_link_protocols(self) -> None:
        with self.assertRaisesRegex(ValueError, "Links must use"):
            validate_structured_content(
                {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "bad",
                                    "marks": [
                                        {"type": "link", "attrs": {"href": "javascript:alert(1)"}}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

    def test_rejects_unsupported_heading_level(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only H1"):
            validate_structured_content(
                {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 4}}]}
            )

    def test_plain_text_preserves_lists_without_extra_blank_lines(self) -> None:
        document = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Intro"}]},
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "one"}]}
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "two"}]}
                            ],
                        },
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "bullet"}]}
                            ],
                        }
                    ],
                },
            ],
        }
        self.assertEqual(rich_text_to_plain_text(document), "Intro\n1. one\n2. two\n• bullet")

    def test_plain_text_removes_redundant_inline_code_ticks(self) -> None:
        document = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "`hello`",
                            "marks": [{"type": "code"}],
                        }
                    ],
                }
            ],
        }
        self.assertEqual(rich_text_to_plain_text(document), "hello")


if __name__ == "__main__":
    unittest.main()
