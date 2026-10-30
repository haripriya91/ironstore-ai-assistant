import pytest

from app.document_registry import (
    discover_documents,
    resolve_document,
    safe_document_path,
)


def test_document_id_is_stable_across_locations(tmp_path):
    relative = "internal_docs_by_area/HR_policies/Policy.pdf"
    roots = [tmp_path / "first", tmp_path / "second"]

    for root in roots:
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"test")

    first = discover_documents(roots[0])[0]
    second = discover_documents(roots[1])[0]

    assert first.document_id == second.document_id
    assert first.department == "People & HR"

    assert resolve_document(
        roots[0], first.document_id, [first]
    ) == (roots[0] / relative).resolve()


def test_rejects_path_outside_document_folder(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"test")

    with pytest.raises(ValueError, match="outside"):
        safe_document_path(root, "../outside.pdf")


def test_rejects_symlink_to_outside_file(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"test")

    (root / "linked.pdf").symlink_to(outside)

    with pytest.raises(ValueError, match="outside"):
        discover_documents(root)


def test_unknown_document_id_is_rejected(tmp_path):
    with pytest.raises(KeyError):
        resolve_document(tmp_path, "unknown-id", [])