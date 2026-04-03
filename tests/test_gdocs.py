"""Tests for Google Docs integration (mocked API)."""

import json
from unittest.mock import MagicMock

import pytest

from vibepaper.diff import Paragraph, ParagraphChange
from vibepaper.gdocs import (
    SyncState,
    build_suggestion_requests,
    get_doc_paragraphs,
    markdown_to_doc_requests,
    save_synced_render,
    load_synced_render,
)


# ---------------------------------------------------------------------------
# markdown_to_doc_requests
# ---------------------------------------------------------------------------

class TestMarkdownToDocRequests:
    def test_heading_gets_style(self):
        requests = markdown_to_doc_requests("# Introduction\n\nSome text.\n")
        types = [list(r.keys())[0] for r in requests]
        assert "insertText" in types
        assert "updateParagraphStyle" in types

    def test_heading_style_matches_level(self):
        requests = markdown_to_doc_requests("## Methods\n")
        style_reqs = [r for r in requests if "updateParagraphStyle" in r]
        assert len(style_reqs) == 1
        style = style_reqs[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
        assert style == "HEADING_2"

    def test_plain_text_inserted(self):
        requests = markdown_to_doc_requests("Just a paragraph.\n")
        insert = [r for r in requests if "insertText" in r]
        assert len(insert) == 1
        assert "Just a paragraph" in insert[0]["insertText"]["text"]

    def test_empty_text_returns_no_requests(self):
        assert markdown_to_doc_requests("") == []
        assert markdown_to_doc_requests("\n\n\n") == []

    def test_multiple_headings(self):
        text = "# Title\n\nText.\n\n## Section\n\nMore text.\n"
        requests = markdown_to_doc_requests(text)
        style_reqs = [r for r in requests if "updateParagraphStyle" in r]
        assert len(style_reqs) == 2
        styles = [r["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
                  for r in style_reqs]
        assert "HEADING_1" in styles
        assert "HEADING_2" in styles

    def test_insert_starts_at_index_1(self):
        requests = markdown_to_doc_requests("Hello.\n")
        insert = [r for r in requests if "insertText" in r][0]
        assert insert["insertText"]["location"]["index"] == 1


# ---------------------------------------------------------------------------
# SyncState
# ---------------------------------------------------------------------------

class TestSyncState:
    def test_save_and_load_roundtrip(self, tmp_path):
        state = SyncState(doc_id="abc123", doc_url="https://docs.google.com/d/abc123/edit")
        state.save(tmp_path)
        loaded = SyncState.load(tmp_path)
        assert loaded.doc_id == "abc123"
        assert loaded.doc_url == "https://docs.google.com/d/abc123/edit"

    def test_load_missing_returns_defaults(self, tmp_path):
        state = SyncState.load(tmp_path)
        assert state.doc_id is None
        assert state.doc_url is None

    def test_save_creates_directory(self, tmp_path):
        state = SyncState(doc_id="x")
        state.save(tmp_path)
        assert (tmp_path / ".vibepaper" / "sync_state.json").exists()

    def test_stored_as_json(self, tmp_path):
        state = SyncState(doc_id="test_id", doc_url="https://example.com")
        state.save(tmp_path)
        data = json.loads((tmp_path / ".vibepaper" / "sync_state.json").read_text())
        assert data["doc_id"] == "test_id"


# ---------------------------------------------------------------------------
# synced render cache
# ---------------------------------------------------------------------------

class TestSyncedRender:
    def test_save_and_load_roundtrip(self, tmp_path):
        text = "# Paper\n\nRendered content.\n"
        save_synced_render(text, tmp_path)
        assert load_synced_render(tmp_path) == text

    def test_load_missing_returns_none(self, tmp_path):
        assert load_synced_render(tmp_path) is None


# ---------------------------------------------------------------------------
# get_doc_paragraphs
# ---------------------------------------------------------------------------

class TestGetDocParagraphs:
    def _mock_service(self, doc_body):
        service = MagicMock()
        service.documents().get().execute.return_value = {
            "body": {"content": doc_body}
        }
        return service

    def test_extracts_text_and_indices(self):
        body = [
            {
                "startIndex": 0,
                "endIndex": 1,
                "sectionBreak": {},
            },
            {
                "startIndex": 1,
                "endIndex": 15,
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "elements": [
                        {"textRun": {"content": "Introduction\n"}}
                    ],
                },
            },
            {
                "startIndex": 15,
                "endIndex": 30,
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [
                        {"textRun": {"content": "Some text here\n"}}
                    ],
                },
            },
        ]
        service = self._mock_service(body)
        paras = get_doc_paragraphs(service, "doc_id")
        assert len(paras) == 2
        assert paras[0]["text"] == "Introduction\n"
        assert paras[0]["style"] == "HEADING_1"
        assert paras[0]["start_index"] == 1
        assert paras[1]["text"] == "Some text here\n"
        assert paras[1]["style"] == "NORMAL_TEXT"

    def test_skips_non_paragraph_elements(self):
        body = [
            {"startIndex": 0, "endIndex": 1, "sectionBreak": {}},
            {"startIndex": 1, "endIndex": 5, "table": {}},
        ]
        service = self._mock_service(body)
        paras = get_doc_paragraphs(service, "doc_id")
        assert len(paras) == 0

    def test_concatenates_multiple_text_runs(self):
        body = [
            {
                "startIndex": 1,
                "endIndex": 20,
                "paragraph": {
                    "elements": [
                        {"textRun": {"content": "Hello "}},
                        {"textRun": {"content": "world\n"}},
                    ],
                },
            },
        ]
        service = self._mock_service(body)
        paras = get_doc_paragraphs(service, "doc_id")
        assert paras[0]["text"] == "Hello world\n"


# ---------------------------------------------------------------------------
# build_suggestion_requests
# ---------------------------------------------------------------------------

def _make_para(kind, text):
    return Paragraph(kind=kind, text=text, line_start=1)


def _make_doc_para(text, start, end, style="NORMAL_TEXT"):
    return {"text": text, "start_index": start, "end_index": end, "style": style}


class TestBuildSuggestionRequests:
    def test_empty_matched_returns_no_requests(self):
        assert build_suggestion_requests([]) == []

    def test_unmatched_changes_skipped(self):
        change = ParagraphChange("changed", _make_para("prose", "old"), _make_para("prose", "new"), "# X")
        assert build_suggestion_requests([(change, None)]) == []

    def test_changed_generates_delete_and_insert(self):
        change = ParagraphChange(
            "changed",
            _make_para("prose", "old text"),
            _make_para("prose", "new text"),
            "# Section",
        )
        doc_para = _make_doc_para("old text\n", 10, 19)
        requests = build_suggestion_requests([(change, doc_para)])
        types = [list(r.keys())[0] for r in requests]
        assert "deleteContentRange" in types
        assert "insertText" in types

    def test_changed_preserves_trailing_newline(self):
        change = ParagraphChange(
            "changed",
            _make_para("prose", "old"),
            _make_para("prose", "new"),
            "# X",
        )
        doc_para = _make_doc_para("old\n", 10, 14)
        requests = build_suggestion_requests([(change, doc_para)])
        delete_req = [r for r in requests if "deleteContentRange" in r][0]
        # Should delete up to 13, not 14 (preserving the trailing newline)
        assert delete_req["deleteContentRange"]["range"]["endIndex"] == 13

    def test_changed_uses_suggestion_ids(self):
        change = ParagraphChange(
            "changed",
            _make_para("prose", "old"),
            _make_para("prose", "new"),
            "# X",
        )
        doc_para = _make_doc_para("old\n", 10, 14)
        requests = build_suggestion_requests([(change, doc_para)])
        delete_req = [r for r in requests if "deleteContentRange" in r][0]
        insert_req = [r for r in requests if "insertText" in r][0]
        # Both should have suggestion IDs
        assert "suggestedDeletionIds" in delete_req["deleteContentRange"]["range"]
        assert "suggestedInsertionIds" in insert_req["insertText"]
        # IDs should match (same suggestion)
        del_id = delete_req["deleteContentRange"]["range"]["suggestedDeletionIds"][0]
        ins_id = insert_req["insertText"]["suggestedInsertionIds"][0]
        assert del_id == ins_id

    def test_removed_generates_delete(self):
        change = ParagraphChange(
            "removed",
            _make_para("prose", "gone"),
            None,
            "# X",
        )
        doc_para = _make_doc_para("gone\n", 5, 10)
        requests = build_suggestion_requests([(change, doc_para)])
        assert len(requests) == 1
        assert "deleteContentRange" in requests[0]
        assert requests[0]["deleteContentRange"]["range"]["startIndex"] == 5
        assert requests[0]["deleteContentRange"]["range"]["endIndex"] == 10

    def test_added_generates_insert(self):
        change = ParagraphChange(
            "added",
            None,
            _make_para("prose", "new paragraph"),
            "# X",
        )
        doc_para = _make_doc_para("context\n", 20, 28)
        requests = build_suggestion_requests([(change, doc_para)])
        assert len(requests) == 1
        assert "insertText" in requests[0]
        assert "new paragraph" in requests[0]["insertText"]["text"]

    def test_multiple_changes_sorted_by_descending_index(self):
        c1 = ParagraphChange("changed", _make_para("prose", "a"), _make_para("prose", "a2"), "# X")
        c2 = ParagraphChange("changed", _make_para("prose", "b"), _make_para("prose", "b2"), "# X")
        dp1 = _make_doc_para("a\n", 10, 12)
        dp2 = _make_doc_para("b\n", 50, 52)
        requests = build_suggestion_requests([(c1, dp1), (c2, dp2)])
        # dp2 (start=50) should come first in requests
        first_start = None
        for r in requests:
            if "deleteContentRange" in r:
                idx = r["deleteContentRange"]["range"]["startIndex"]
                if first_start is None:
                    first_start = idx
                    assert idx == 50
                    break
