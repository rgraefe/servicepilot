from __future__ import annotations

import json
from pathlib import Path

from conversation.knowledge_hierarchy import parse_markdown_file


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "data" / "knowledge"


def _manifest() -> dict:
    return json.loads((KNOWLEDGE / "corpus.json").read_text(encoding="utf-8"))


def test_corpus_contains_phase_seven_documents_and_generated_pdfs() -> None:
    manifest = _manifest()
    assert manifest["chunking"] == {
        "method": "layout-aware-hierarchical",
        "chunk_size_tokens": 300,
        "include_ancestor_headings": True,
    }
    assert {item["document_type"] for item in manifest["documents"]} == {
        "manual", "error_codes", "warranty", "faq"
    }
    assert {item["model"] for item in manifest["documents"]} >= {
        "HeatPump-X200", "HeatPump-X300"
    }
    for item in manifest["documents"]:
        pdf = KNOWLEDGE / item["pdf"]
        assert pdf.read_bytes().startswith(b"%PDF-")


def test_leaf_chunks_retain_full_ancestor_heading_path() -> None:
    document = next(item for item in _manifest()["documents"] if item["model"] == "HeatPump-X200")
    chunks = parse_markdown_file(document["id"], KNOWLEDGE / document["source"])
    e37 = next(chunk for chunk in chunks if "Volumenstrom" in chunk.text)
    assert e37.heading_path == (
        "HeatPump-X200 Bedienungs- und Servicehandbuch",
        "Fehlerdiagnose",
        "Fehler E37 – Volumenstrom zu niedrig",
    )
    assert "Fehlerdiagnose > Fehler E37" in e37.retrieval_text


def test_conflicting_code_meanings_force_model_clarification() -> None:
    chunks = []
    for item in _manifest()["documents"]:
        chunks.extend(parse_markdown_file(item["id"], KNOWLEDGE / item["source"]))
    meanings = {
        chunk.heading_path[0]: chunk.text
        for chunk in chunks
        if chunk.heading_path[-1].startswith("Fehler E37")
    }
    assert "Volumenstrom" in meanings["HeatPump-X200 Bedienungs- und Servicehandbuch"]
    assert "Kommunikation" in meanings["HeatPump-X300 Bedienungs- und Servicehandbuch"]


def test_knowledge_playbook_covers_citation_unknown_and_conflict_paths() -> None:
    catalog = json.loads((ROOT / "conversation" / "catalog.json").read_text(encoding="utf-8"))
    playbook = next(item for item in catalog["playbooks"] if item["name"] == "KnowledgeSupport")
    examples = {example["name"]: example for example in playbook["examples"]}
    assert playbook["tools"] == ["ServicePilotKnowledge", "ServicePilotBackend"]
    assert "Quelle:" in examples["verified reset guidance"]["agent"]
    assert examples["unknown code"]["tool"]["output"]["snippets"] == []
    assert examples["conflicting model meanings"]["state"] == "PENDING"
    assert "Welches Modell" in examples["conflicting model meanings"]["agent"]


def test_deployment_uses_layout_parser_and_ancestor_headings() -> None:
    script = (ROOT / "scripts" / "deploy-knowledge-rag.ps1").read_text(encoding="utf-8")
    assert "layoutParsingConfig" in script
    assert "includeAncestorHeadings=$true" in script
    assert "dataSchema='document'" in script
    assert "ServicePilotKnowledge" in script
    acceptance = (ROOT / "scripts" / "test-knowledge-rag.ps1").read_text(encoding="utf-8")
    assert "snippetSpec" in acceptance
    assert "extractiveContentSpec" not in acceptance
    assert "HeatPump-X300 Bedienungs- und Servicehandbuch" in acceptance
