"""Exact extraction spans, independent offline guards and complete embedding batches."""

import asyncio
from io import BytesIO

import pytest


def test_html_sections_and_exact_spans():
    from app.knowledge_sources import extract_source

    raw = b"<html><script>ignored()</script><h2>Eligibility</h2><p>Rule &amp; exception.</p><h2>Renewal</h2><p>Next rule.</p></html>"
    parsed = extract_source(raw, "text/html")
    assert [(c.section, c.text) for c in parsed.chunks] == [
        ("Eligibility", "Rule & exception."),
        ("Renewal", "Next rule."),
    ]
    assert all(parsed.text[c.char_start : c.char_end] == c.text for c in parsed.chunks)
    assert "ignored" not in parsed.text


def test_pdf_page_locator_and_empty_password():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from app.knowledge_sources import extract_source

    writer = PdfWriter()
    for value in ("First page", "Second page"):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf ({value}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    writer.encrypt("", algorithm="AES-256")
    out = BytesIO()
    writer.write(out)
    parsed = extract_source(out.getvalue(), "application/pdf")
    assert [(c.page, c.text) for c in parsed.chunks] == [
        (1, "First page"),
        (2, "Second page"),
    ]
    assert all(parsed.text[c.char_start : c.char_end] == c.text for c in parsed.chunks)


def test_unknown_source_and_independent_network_guards(monkeypatch):
    from app.embeddings import EmbeddingUnavailable, GatewayEmbeddings
    from app.knowledge_sources import SourceError, fetch_source, source_by_key

    with pytest.raises(SourceError):
        source_by_key("https://example.test/upload")
    with pytest.raises(SourceError, match="disabled"):
        asyncio.run(fetch_source(source_by_key("dentist-application")))
    with pytest.raises(EmbeddingUnavailable, match="disabled"):
        asyncio.run(GatewayEmbeddings().embed(["synthetic"]))


@pytest.mark.parametrize(
    "vectors", [[], [[1]], [[0, 0]], [[float("inf"), 1]], [[float("nan"), 1]]]
)
def test_reject_invalid_batch(vectors):
    from app.embeddings import EmbeddingUnavailable, validate_vectors

    with pytest.raises(EmbeddingUnavailable):
        validate_vectors(vectors, 1, 2)


def test_gateway_orders_vectors_and_sanitizes_errors(monkeypatch):
    import httpx

    from app.embeddings import EmbeddingUnavailable, GatewayEmbeddings

    monkeypatch.delenv("DISABLE_EMBEDDING_REQUESTS")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "2")
    monkeypatch.setenv("LLM_API_GATEWAY", "https://synthetic.invalid/v1")
    monkeypatch.setenv("LLM_API_TOKEN", "synthetic-token")
    client_type = httpx.AsyncClient

    def transport(request):
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0, 1]},
                    {"index": 0, "embedding": [1, 0]},
                ]
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: client_type(transport=httpx.MockTransport(transport), **kw),
    )
    assert asyncio.run(GatewayEmbeddings().embed(["first", "second"])) == [
        [1, 0],
        [0, 1],
    ]

    def failed(request):
        return httpx.Response(500, text="unexpected sensitive response")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: client_type(transport=httpx.MockTransport(failed), **kw),
    )
    with pytest.raises(EmbeddingUnavailable) as exc:
        asyncio.run(GatewayEmbeddings().embed(["synthetic"]))
    assert "synthetic-token" not in str(exc.value)
    assert "sensitive response" not in str(exc.value)


def test_original_fetch_refuses_redirects_and_html_instead_of_pdf(monkeypatch):
    import httpx

    from app.knowledge_sources import SourceError, fetch_source, source_by_key

    monkeypatch.delenv("DISABLE_SOURCE_FETCH")
    client_type = httpx.AsyncClient
    source = source_by_key("dentist-application")
    for response in [
        httpx.Response(302, headers={"Location": "https://outside.invalid"}),
        httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"Sign in"),
    ]:

        def handler(req, response=response):
            assert str(req.url) == source.url
            return response

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw),
        )
        with pytest.raises(SourceError):
            asyncio.run(fetch_source(source))


def test_legacy_statute_html_charset_keeps_section_symbol():
    from app.knowledge_sources import extract_source

    raw = b'<meta http-equiv="Content-Type" content="text/html; charset=windows-1252"><p>\xa7 448-9. Application.</p>'
    parsed = extract_source(raw, "text/html")
    assert parsed.chunks[0].text == "§ 448-9. Application."
