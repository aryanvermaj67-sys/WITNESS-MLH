import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import server
from pdfmaker import HANDBOOK, make_pdf
from witness import cache, documents, generator, judge_gemma, pipeline
from witness.config import settings
from witness.models import DocumentInfo, PipelineResult
from witness.retrieval import load_embedder


@pytest.fixture(scope="module")
def embedder():
    return load_embedder(settings.EMBED_MODEL)


# ---- reading the PDF ---------------------------------------------------------------------------
def test_wrapped_lines_and_hyphenation_are_repaired():
    passages, titles = documents.build_passages("handbook.pdf", documents.read_pages(make_pdf(HANDBOOK)))
    sentences = [s.text for p in passages for s in p.sentences]
    assert "Teams may have up to five members and every member must be at least sixteen years old." in sentences
    assert "The final report is due on Friday at noon." in sentences
    assert "Late reports are not accepted under any circumstances." in sentences  # "circum-\nstances" joined
    assert "Project Alpha Handbook" in sentences and "Prizes" in sentences  # headings stay on their own
    assert "The winning team receives a trophy and a cash award of two hundred dollars." in sentences
    ids = [s.id for p in passages for s in p.sentences]
    assert len(ids) == len(set(ids)) and all(s.id.startswith(p.id + ".s") for p in passages for s in p.sentences)
    assert all(p.doc == "handbook.pdf" and p.text == " ".join(s.text for s in p.sentences) for p in passages)
    assert set(titles) == {p.id for p in passages}
    assert documents.build_passages("handbook.pdf", documents.read_pages(make_pdf(HANDBOOK))) == (passages, titles)  # stable


def test_control_characters_and_replacement_symbols_are_removed():
    dirty = "Teams may have five members.\x7f\nEvery member\x07 must register.� Late entries are refused.\x00"
    text = " ".join(documents._unwrap(dirty))
    assert not any(ord(c) < 32 and c not in "\t\n\r" or c in "\x7f�" for c in text)
    assert "Teams may have five members." in text and "Late entries are refused." in text
    pdf_text = documents.read_pages(make_pdf([["Bullet \x7f item one is here.", "Second bullet item is here too."]]))
    assert "\x7f" not in " ".join(documents._unwrap(pdf_text[0]))


def test_passages_never_cross_pages_and_stay_short():
    long_page = ["Sentence number %d is a perfectly ordinary sentence about the project plan." % i for i in range(60)]
    passages, titles = documents.build_passages("long.pdf", documents.read_pages(make_pdf([long_page, ["Short second page here with words."]])))
    assert all(len(p.text.split()) <= 150 for p in passages)
    assert "page 1" in titles[passages[0].id] and "page 2" in titles[passages[-1].id]


def test_bad_files_get_friendly_errors(monkeypatch):
    with pytest.raises(documents.DocumentError, match="not a PDF"):
        documents.read_pages(b"hello, this is plain text")
    with pytest.raises(documents.DocumentError, match="could not be read"):
        documents.read_pages(b"%PDF-1.4 this is not really a pdf")
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(documents.DocumentError, match="password"):
        documents.read_pages(buf.getvalue())
    monkeypatch.setattr(documents, "MAX_PAGES", 1)
    with pytest.raises(documents.DocumentError, match="more than 1 pages"):
        documents.read_pages(make_pdf(HANDBOOK))
    monkeypatch.setattr(documents, "MAX_BYTES", 100)
    with pytest.raises(documents.DocumentError, match="larger than 10 MB"):
        documents.read_pages(make_pdf(HANDBOOK))


def test_a_pdf_without_text_is_rejected(embedder):
    store = documents.DocumentStore(embedder)
    with pytest.raises(documents.DocumentError, match="No readable text"):
        store.add("scan.pdf", make_pdf([[""]]))
    with pytest.raises(documents.DocumentError, match="No readable text"):
        store.add("tiny.pdf", make_pdf([["Just five words here."]]))


def test_name_is_cleaned():
    assert documents.clean_name("C:\\Users\\me\\My Notes.pdf") == "My Notes.pdf"
    assert documents.clean_name("../../etc/passwd") == "passwd"
    assert documents.clean_name("") == "document.pdf" and len(documents.clean_name("x" * 500)) == 100


# ---- the store ---------------------------------------------------------------------------------
FILLER = [[f"The {topic} chapter explains how {topic} work and why people enjoy visiting {topic} on quiet weekends."]
          for topic in ("gardens", "railways", "rivers", "orchestras", "kitchens", "telescopes", "harbours", "libraries")]


def test_store_search_reuse_eviction_and_remove(embedder, monkeypatch):
    store = documents.DocumentStore(embedder)
    doc = store.add("handbook.pdf", make_pdf(HANDBOOK + FILLER))  # keyword search needs more than a couple of passages
    assert (doc.name, doc.pages) == ("handbook.pdf", 10) and doc.words > 20
    top = doc.retriever.search("How many members can a team have?", 1, 60)[0]
    assert "five members" in top.text
    assert "trophy" in doc.retriever.search("What prize does the winning team receive, a trophy?", 1, 60)[0].text
    assert store.add("renamed.pdf", make_pdf(HANDBOOK + FILLER)) is doc  # identical bytes: reused, not rebuilt
    assert [d.id for d in store.list()] == [doc.id] and store.get("nope") is None

    monkeypatch.setattr(documents, "MAX_DOCS", 2)
    a = store.add("a.pdf", make_pdf([["Alpha pages talk about the moon and its many craters and seas."] * 3]))
    b = store.add("b.pdf", make_pdf([["Beta pages talk about the ocean and its many currents and tides."] * 3]))
    assert store.get(doc.id) is None and store.get(a.id) and store.get(b.id)  # the oldest upload was dropped
    assert store.remove(a.id) and not store.remove(a.id)


# ---- the HTTP routes ---------------------------------------------------------------------------
@pytest.fixture
def client(embedder, monkeypatch):
    server.app.state.documents = documents.DocumentStore(embedder)
    monkeypatch.setattr(generator, "generate", lambda q, p: ("Teams may have five members. Reports are due on Friday.", None))
    monkeypatch.setattr(judge_gemma, "judge", lambda p, c: ({}, []))
    return TestClient(server.app)


def upload(client, data, name="handbook.pdf"):
    return client.post(f"/api/documents?name={name}", content=data, headers={"Content-Type": "application/pdf"})


def test_upload_list_check_and_delete(client):
    r = upload(client, make_pdf(HANDBOOK))
    assert r.status_code == 200
    info = DocumentInfo.model_validate(r.json())
    assert (info.name, info.pages) == ("handbook.pdf", 2) and info.passages >= 2 and info.sentences >= 5
    assert client.get("/api/documents").json() == [r.json()]

    index_before = cache.load_index()
    res = client.post("/api/check", json={"question": "How many members can a team have?", "document_id": info.id})
    assert res.status_code == 200
    result = PipelineResult.model_validate(res.json())
    assert result.mode == "live" and result.passages and all(p.doc == "handbook.pdf" for p in result.passages)
    assert "five members" in " ".join(p.text for p in result.passages)
    assert cache.load_index() == index_before  # a private document is never saved for replay

    pasted = client.post("/api/check", json={"question": "q", "answer_text": "Teams may have five members here.", "document_id": info.id}).json()
    assert pasted["answer_source"] == "pasted" and all(p["doc"] == "handbook.pdf" for p in pasted["passages"])

    assert client.delete(f"/api/documents/{info.id}").status_code == 200
    assert client.delete(f"/api/documents/{info.id}").status_code == 404
    assert client.get("/api/documents").json() == []


def test_check_with_an_unknown_document_is_still_200(client):
    r = client.post("/api/check", json={"question": "q", "document_id": "gone"})
    assert r.status_code == 200
    j = r.json()
    assert j["claims"] == [] and j["errors"] == ["That document is no longer loaded. Upload the PDF again."]
    PipelineResult.model_validate(j)


def test_upload_errors(client, monkeypatch):
    r = upload(client, b"just some text", "notes.txt")
    assert (r.status_code, r.json()["detail"]) == (422, "That file is not a PDF.")
    assert upload(client, make_pdf([[""]])).status_code == 422
    monkeypatch.setattr(documents, "MAX_BYTES", 200)
    r = upload(client, make_pdf(HANDBOOK))
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]


def test_upload_before_the_index_is_loaded_is_a_clear_503():
    if hasattr(server.app.state, "documents"):
        del server.app.state.documents
    r = TestClient(server.app).post("/api/documents", content=make_pdf(HANDBOOK))
    assert r.status_code == 503


def test_normal_checks_still_save_to_replay_but_documents_do_not(client, monkeypatch):
    saved = []
    monkeypatch.setattr(cache, "save_result", lambda result: saved.append(result.question))

    passage = documents.build_passages("h.pdf", documents.read_pages(make_pdf(HANDBOOK)))[0][:1]

    class Retriever:
        def search(self, *a):
            return passage
    pipeline.run_pipeline("normal question", None, Retriever(), None)  # the writer mock gives 2 claims: saved
    pipeline.run_pipeline("private question", None, Retriever(), None, save=False)
    assert saved == ["normal question"]
