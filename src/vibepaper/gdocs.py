"""Google Docs integration for vibepaper.

Sync rendered markdown to a Google Doc, pushing paragraph-level changes
as suggestions (tracked changes) so collaborator comments are preserved.

Requires: pip install vibepaper[sync]
"""

import difflib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/documents"]
CREDENTIALS_DIR = ".vibepaper"
TOKEN_FILE = "token.json"
SYNC_STATE_FILE = "sync_state.json"
LAST_SYNCED_FILE = "last_synced.md"


def _check_imports():
    """Raise a clear error if the sync extras are not installed."""
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Google Docs sync requires extra dependencies.\n"
            "Install them with:  pip install vibepaper[sync]"
        )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_credentials(project_root: Path):
    """Obtain OAuth2 credentials, prompting for browser auth if needed.

    Expects .vibepaper/credentials.json (OAuth client secret downloaded
    from Google Cloud Console).  Stores refresh token in
    .vibepaper/token.json (should be .gitignored).
    """
    _check_imports()
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    cred_dir = project_root / CREDENTIALS_DIR
    token_path = cred_dir / TOKEN_FILE
    client_secret = cred_dir / "credentials.json"

    if not client_secret.exists():
        raise FileNotFoundError(
            f"Google OAuth client secret not found at {client_secret}.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials\n"
            "and save it as .vibepaper/credentials.json"
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def get_docs_service(project_root: Path):
    """Build and return a Google Docs API service object."""
    _check_imports()
    from googleapiclient.discovery import build as build_service
    creds = get_credentials(project_root)
    return build_service("docs", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

@dataclass
class SyncState:
    """Persistent state for a synced Google Doc."""
    doc_id: str | None = None
    doc_url: str | None = None

    @classmethod
    def load(cls, project_root: Path) -> "SyncState":
        path = project_root / CREDENTIALS_DIR / SYNC_STATE_FILE
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return cls()

    def save(self, project_root: Path):
        path = project_root / CREDENTIALS_DIR / SYNC_STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "doc_id": self.doc_id,
            "doc_url": self.doc_url,
        }, indent=2))


def save_synced_render(text: str, project_root: Path) -> Path:
    """Save the full rendered text that was last synced."""
    path = project_root / CREDENTIALS_DIR / LAST_SYNCED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def load_synced_render(project_root: Path) -> str | None:
    """Load the text from the last sync, or None."""
    path = project_root / CREDENTIALS_DIR / LAST_SYNCED_FILE
    return path.read_text() if path.exists() else None


# ---------------------------------------------------------------------------
# Create a Google Doc from markdown
# ---------------------------------------------------------------------------

def markdown_to_doc_requests(text: str) -> list[dict]:
    """Convert rendered markdown to Google Docs API batchUpdate requests.

    Inserts all text first, then applies heading styles.  Google Docs
    body content starts at index 1.
    """
    from .diff import parse_paragraphs

    paragraphs = parse_paragraphs(text)
    full_text = ""
    heading_ranges: list[tuple[int, int, int]] = []  # (start, end, level)

    for para in paragraphs:
        para_text = para.text.strip()
        if not para_text:
            continue

        if para.kind == "heading":
            match = re.match(r"^(#{1,6})\s+(.*)", para_text)
            if match:
                level = len(match.group(1))
                heading_text = match.group(2) + "\n"
                start = len(full_text) + 1  # Docs 1-based indexing
                full_text += heading_text
                heading_ranges.append((start, len(full_text) + 1, level))
                continue

        full_text += para_text + "\n\n"

    requests: list[dict] = []
    if not full_text:
        return requests

    requests.append({
        "insertText": {
            "location": {"index": 1},
            "text": full_text,
        }
    })

    style_map = {i: f"HEADING_{i}" for i in range(1, 7)}
    for start, end, level in heading_ranges:
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style_map[level]},
                "fields": "namedStyleType",
            }
        })

    return requests


def create_doc(service, title: str, text: str) -> str:
    """Create a new Google Doc with the given content.  Returns the doc ID."""
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    requests = markdown_to_doc_requests(text)
    if requests:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests},
        ).execute()

    return doc_id


# ---------------------------------------------------------------------------
# Read Google Doc paragraphs
# ---------------------------------------------------------------------------

def get_doc_paragraphs(service, doc_id: str) -> list[dict]:
    """Fetch a Google Doc and return its paragraphs with text and indices.

    Each returned dict has keys: text, start_index, end_index, style.
    """
    doc = service.documents().get(documentId=doc_id).execute()
    paragraphs = []
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" not in element:
            continue
        para = element["paragraph"]
        text = "".join(
            pe.get("textRun", {}).get("content", "")
            for pe in para.get("elements", [])
        )
        paragraphs.append({
            "text": text,
            "start_index": element["startIndex"],
            "end_index": element["endIndex"],
            "style": para.get("paragraphStyle", {}).get(
                "namedStyleType", "NORMAL_TEXT"
            ),
        })
    return paragraphs


# ---------------------------------------------------------------------------
# Paragraph matching
# ---------------------------------------------------------------------------

def match_paragraphs(
    local_changes: list,
    doc_paragraphs: list[dict],
) -> list[tuple]:
    """Match local changed paragraphs to Google Doc paragraphs.

    For each change, finds the best-matching Doc paragraph by fuzzy text
    similarity.  Returns (ParagraphChange, doc_paragraph | None) tuples.
    """
    matched = []
    for change in local_changes:
        # For "changed" and "removed", match using the OLD text (what the
        # Doc should still contain).  For "added", we need a location —
        # match using the new text's nearest context.
        source = change.old if change.old else change.new
        if not source:
            matched.append((change, None))
            continue

        best_match = None
        best_ratio = 0.0
        source_text = source.fingerprint()

        for dp in doc_paragraphs:
            ratio = difflib.SequenceMatcher(
                None, source_text, dp["text"].strip()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = dp

        # Require at least 40% similarity to accept a match
        if best_ratio > 0.4:
            matched.append((change, best_match))
        else:
            matched.append((change, None))
            log.warning(
                "Could not match paragraph to Google Doc (best ratio %.2f): %s",
                best_ratio, source_text[:80],
            )

    return matched


# ---------------------------------------------------------------------------
# Build suggestion requests
# ---------------------------------------------------------------------------

def build_suggestion_requests(matched: list[tuple]) -> list[dict]:
    """Build batchUpdate requests to push changes as suggestions.

    For "changed": suggest-delete old text, suggest-insert new text.
    For "added": suggest-insert at the nearest matched location.
    For "removed": suggest-delete the paragraph.

    Requests are sorted by descending index so earlier indices stay valid.
    """
    requests: list[dict] = []
    items = [(c, dp) for c, dp in matched if dp is not None]
    items.sort(key=lambda x: x[1]["start_index"], reverse=True)

    for change, doc_para in items:
        suggestion_id = str(uuid.uuid4())

        if change.action == "changed":
            # Don't delete the trailing newline — that would merge paragraphs
            delete_end = doc_para["end_index"]
            if doc_para["text"].endswith("\n"):
                delete_end -= 1

            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": doc_para["start_index"],
                        "endIndex": delete_end,
                        "suggestedDeletionIds": [suggestion_id],
                    }
                }
            })
            requests.append({
                "insertText": {
                    "location": {"index": doc_para["start_index"]},
                    "text": change.new.text.strip(),
                    "suggestedInsertionIds": [suggestion_id],
                }
            })

        elif change.action == "removed":
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": doc_para["start_index"],
                        "endIndex": doc_para["end_index"],
                        "suggestedDeletionIds": [suggestion_id],
                    }
                }
            })

        elif change.action == "added":
            requests.append({
                "insertText": {
                    "location": {"index": doc_para["end_index"]},
                    "text": "\n" + change.new.text.strip() + "\n",
                    "suggestedInsertionIds": [suggestion_id],
                }
            })

    return requests


# ---------------------------------------------------------------------------
# High-level sync
# ---------------------------------------------------------------------------

def sync_to_doc(service, doc_id: str, changes: list) -> int:
    """Push paragraph-level changes to a Google Doc as suggestions.

    Returns the number of changes successfully matched and applied.
    """
    doc_paras = get_doc_paragraphs(service, doc_id)
    matched = match_paragraphs(changes, doc_paras)
    requests = build_suggestion_requests(matched)
    if not requests:
        return 0

    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()

    return len([c for c, dp in matched if dp is not None])
