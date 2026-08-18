from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import fitz


ALLOWED_HOSTS = {
    "gov.br",
    "in.gov.br",
    "ioepa.com.br",
    "belem.pa.gov.br",
}
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (compatible; LeitorDiariosOficiais/1.0; "
    "+monitoramento de publicacoes oficiais)"
)


class OfficialDocumentError(RuntimeError):
    pass


@dataclass
class DownloadedDocument:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    byte_count: int
    sha256: str
    downloaded_at_utc: str
    data: bytes

    def public_metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("data")
        return result


def is_allowed_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.rstrip(".").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_HOSTS)


def validate_official_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise OfficialDocumentError("A URL deve usar HTTPS.")
    if parsed.username or parsed.password:
        raise OfficialDocumentError("A URL não pode conter usuário ou senha.")
    if not is_allowed_host(parsed.hostname):
        raise OfficialDocumentError(
            "Domínio não autorizado. Use apenas portais oficiais do DOU, "
            "DOE-PA, gov.br ou Prefeitura de Belém."
        )
    return url


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = validate_official_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def _single_download(url: str) -> tuple[bytes, str, int, str]:
    validated_url = validate_official_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"}
    opener = build_opener(_SafeRedirectHandler())
    request = Request(validated_url, headers=headers, method="GET")
    with opener.open(request, timeout=300) as response:
        final_url = validate_official_url(response.geturl())
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise OfficialDocumentError("O documento excede o limite de 80 MB.")
            chunks.append(chunk)
        return (
            b"".join(chunks),
            final_url,
            response.status,
            response.headers.get_content_type().lower(),
        )


def download_official_document(url: str, attempts: int = 5) -> DownloadedDocument:
    validate_official_url(url)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            data, final_url, status_code, content_type = _single_download(url)
            return DownloadedDocument(
                requested_url=url,
                final_url=final_url,
                status_code=status_code,
                content_type=content_type,
                byte_count=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                downloaded_at_utc=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                data=data,
            )
        except (HTTPError, URLError, TimeoutError, OfficialDocumentError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 8))
    raise OfficialDocumentError(f"Falha após {attempts} tentativas: {last_error}")


def is_pdf(document: DownloadedDocument) -> bool:
    return document.data.startswith(b"%PDF-")


def pdf_metadata(document: DownloadedDocument) -> dict[str, Any]:
    if not is_pdf(document):
        raise OfficialDocumentError("O conteúdo recebido não é um PDF válido.")
    with fitz.open(stream=document.data, filetype="pdf") as pdf:
        return {
            **document.public_metadata(),
            "document_type": "pdf",
            "page_count": pdf.page_count,
            "pdf_metadata": {k: v for k, v in pdf.metadata.items() if v},
        }


def extract_pdf_pages(
    document: DownloadedDocument,
    start_page: int,
    end_page: int,
    character_limit: int,
) -> dict[str, Any]:
    if not is_pdf(document):
        raise OfficialDocumentError("O conteúdo recebido não é um PDF válido.")
    if start_page < 1 or end_page < start_page:
        raise OfficialDocumentError("Intervalo de páginas inválido.")
    if character_limit < 1_000 or character_limit > 100_000:
        raise OfficialDocumentError("O limite deve estar entre 1.000 e 100.000 caracteres.")

    with fitz.open(stream=document.data, filetype="pdf") as pdf:
        if start_page > pdf.page_count:
            raise OfficialDocumentError(f"O PDF possui somente {pdf.page_count} páginas.")
        actual_end = min(end_page, pdf.page_count)
        parts: list[str] = []
        truncated = False
        for page_number in range(start_page, actual_end + 1):
            text = pdf.load_page(page_number - 1).get_text("text")
            candidate = f"\n\n--- Página {page_number} ---\n{text}"
            if sum(len(part) for part in parts) + len(candidate) > character_limit:
                remaining = character_limit - sum(len(part) for part in parts)
                if remaining > 0:
                    parts.append(candidate[:remaining])
                truncated = True
                break
            parts.append(candidate)

        return {
            **document.public_metadata(),
            "document_type": "pdf",
            "page_count": pdf.page_count,
            "requested_pages": [start_page, end_page],
            "returned_through_page": actual_end if not truncated else None,
            "truncated": truncated,
            "text": "".join(parts).strip(),
        }


def search_pdf(
    document: DownloadedDocument,
    terms: list[str],
    max_results: int,
) -> dict[str, Any]:
    if not is_pdf(document):
        raise OfficialDocumentError("O conteúdo recebido não é um PDF válido.")
    cleaned_terms = [term.strip() for term in terms if term.strip()]
    if not cleaned_terms:
        raise OfficialDocumentError("Informe ao menos um termo de pesquisa.")
    if max_results < 1 or max_results > 100:
        raise OfficialDocumentError("max_results deve estar entre 1 e 100.")

    patterns = [re.compile(re.escape(term), re.IGNORECASE) for term in cleaned_terms]
    results: list[dict[str, Any]] = []
    with fitz.open(stream=document.data, filetype="pdf") as pdf:
        for page_index in range(pdf.page_count):
            text = pdf.load_page(page_index).get_text("text")
            normalized = re.sub(r"\s+", " ", text).strip()
            for term, pattern in zip(cleaned_terms, patterns):
                for match in pattern.finditer(normalized):
                    start = max(0, match.start() - 220)
                    end = min(len(normalized), match.end() + 420)
                    results.append(
                        {
                            "term": term,
                            "page": page_index + 1,
                            "snippet": normalized[start:end],
                        }
                    )
                    if len(results) >= max_results:
                        return {
                            **document.public_metadata(),
                            "page_count": pdf.page_count,
                            "terms": cleaned_terms,
                            "result_count": len(results),
                            "truncated": True,
                            "results": results,
                        }
        return {
            **document.public_metadata(),
            "page_count": pdf.page_count,
            "terms": cleaned_terms,
            "result_count": len(results),
            "truncated": False,
            "results": results,
        }


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not cleaned or self.hidden_depth:
            return
        self.text_parts.append(cleaned)
        if self.in_title:
            self.title_parts.append(cleaned)


def extract_html(document: DownloadedDocument, character_limit: int) -> dict[str, Any]:
    if character_limit < 1_000 or character_limit > 100_000:
        raise OfficialDocumentError("O limite deve estar entre 1.000 e 100.000 caracteres.")
    parser = _VisibleTextParser()
    parser.feed(document.data.decode("utf-8", errors="replace"))
    text = "\n".join(parser.text_parts)
    return {
        **document.public_metadata(),
        "document_type": "html",
        "title": " ".join(parser.title_parts) or None,
        "truncated": len(text) > character_limit,
        "text": text[:character_limit],
    }
