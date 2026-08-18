from __future__ import annotations

from datetime import datetime

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from core import (
    OfficialDocumentError,
    download_official_document,
    extract_html,
    extract_pdf_pages,
    is_pdf,
    pdf_metadata,
    search_pdf,
)


mcp = FastMCP(
    "Leitor de Diários Oficiais",
    instructions=(
        "Ferramentas somente de leitura para consultar e validar documentos oficiais "
        "do DOU, DOE-PA, gov.br e Diário Oficial do Município de Belém. Sempre preserve "
        "a URL oficial, o hash e a página usada como evidência."
    ),
    stateless_http=True,
    json_response=True,
)


def _error(exc: Exception) -> dict:
    return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


@mcp.tool()
def verificar_documento_oficial(url: str) -> dict:
    """Baixa uma URL oficial e retorna metadados, hash e quantidade de páginas do PDF."""
    try:
        document = download_official_document(url)
        if is_pdf(document):
            return {"ok": True, **pdf_metadata(document)}
        return {
            "ok": True,
            **document.public_metadata(),
            "document_type": "html_or_other",
            "warning": "O conteúdo não começa com a assinatura %PDF-.",
        }
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def extrair_documento_oficial(
    url: str,
    pagina_inicial: int = 1,
    pagina_final: int = 10,
    limite_caracteres: int = 60_000,
) -> dict:
    """Extrai páginas de um PDF oficial ou texto de uma página HTML oficial."""
    try:
        document = download_official_document(url)
        if is_pdf(document):
            return {
                "ok": True,
                **extract_pdf_pages(document, pagina_inicial, pagina_final, limite_caracteres),
            }
        return {"ok": True, **extract_html(document, limite_caracteres)}
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def pesquisar_pdf_oficial(
    url: str,
    termos: list[str],
    max_resultados: int = 40,
) -> dict:
    """Pesquisa termos em todas as páginas de um PDF oficial e retorna páginas e trechos."""
    try:
        document = download_official_document(url)
        return {"ok": True, **search_pdf(document, termos, max_resultados)}
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def verificar_edicoes_ioepa(data: str) -> dict:
    """Verifica as URLs previsíveis das edições regular e extra do DOE-PA em AAAA-MM-DD."""
    try:
        parsed = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return _error(OfficialDocumentError("Use a data no formato AAAA-MM-DD."))

    prefix = parsed.strftime("%Y.%m.%d")
    year = parsed.strftime("%Y")
    candidates = {
        "regular": f"https://www.ioepa.com.br/pages/{year}/{prefix}.DOE.pdf",
        "extra": f"https://www.ioepa.com.br/pages/{year}/{prefix}.EXTRA.pdf",
    }
    results = {}
    for edition_type, url in candidates.items():
        try:
            document = download_official_document(url)
            results[edition_type] = {"exists": True, **pdf_metadata(document)}
        except Exception as exc:
            results[edition_type] = {"exists": False, "url": url, "error": str(exc)}
    return {"ok": True, "date": data, "editions": results}


@mcp.tool()
def obter_links_dou(data: str) -> dict:
    """Gera os links oficiais de consulta das três seções regulares do DOU para uma data."""
    try:
        parsed = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return _error(OfficialDocumentError("Use a data no formato AAAA-MM-DD."))
    formatted = parsed.strftime("%d-%m-%Y")
    return {
        "ok": True,
        "date": data,
        "links": {
            "secao_1": f"https://www.in.gov.br/leiturajornal?data={formatted}&secao=do1",
            "secao_2": f"https://www.in.gov.br/leiturajornal?data={formatted}&secao=do2",
            "secao_3": f"https://www.in.gov.br/leiturajornal?data={formatted}&secao=do3",
            "consulta": (
                "https://www.in.gov.br/consulta/-/buscar/dou"
                f"?exactDate=personalizado&publishFrom={parsed.strftime('%d/%m/%Y')}"
                f"&publishTo={parsed.strftime('%d/%m/%Y')}"
            ),
        },
        "warning": "Os links são oficiais, mas esta ferramenta não afirma que a edição existe.",
    }


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "leitor-diarios-oficiais"})


app = mcp.streamable_http_app()
app.router.add_route("/health", health, methods=["GET"])

