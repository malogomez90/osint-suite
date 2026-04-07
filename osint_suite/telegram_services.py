"""
Servicios de aplicación para el bot de Telegram.

Los handlers del bot deben delegar aquí y mantener la lógica OSINT dentro de
las herramientas existentes del paquete.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, Sequence

from .company_research import CompanyResearcher
from .document_analyzer import DocumentAnalyzer
from .email_osint import EmailOSINT
from .geolocation_helper import GeolocationHelper
from .image_metadata import ImageMetadataExtractor
from .phone_investigator import PhoneInvestigator
from .social_analyzer import SocialMediaAnalyzer
from .username_search import UsernameSearcher
from .breach_checker import BreachChecker


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
GENERIC_ARGUMENT_ERROR = "Solicitud invalida. Revisa los parametros e intenta de nuevo."
CONTROLLED_TOOL_FAILURE = "No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde."
UNSUPPORTED_DOCUMENT_ERROR = "Formato de documento no soportado. Envia PDF u Office/OpenDocument."
UNSUPPORTED_IMAGE_ERROR = "Formato de imagen no soportado."
EMPTY_UPLOAD_ERROR = "Archivo vacio o sin contenido."
CORRUPTED_UPLOAD_ERROR = "Archivo corrupto o no coincide con el tipo esperado."
SERVICE_USAGE: Dict[str, str] = {
    "username": "Solicitud invalida. Usa /username <usuario>.",
    "email": "Solicitud invalida. Usa /email <email>.",
    "phone": "Solicitud invalida. Usa /phone <numero> [--region XX].",
    "company": "Solicitud invalida. Usa /company <nombre> [--country XX].",
    "geo": "Solicitud invalida. Usa /geo <lat, lon>.",
    "social": "Solicitud invalida. Usa /social <usuario>.",
    "breach": "Solicitud invalida. Usa /breach <email|usuario>.",
}


class ControlledServiceError(RuntimeError):
    pass


class FileServiceError(ValueError):
    pass


@dataclass
class CommandResult:
    summary: str
    payload: Dict[str, Any]
    filename_prefix: str

    @property
    def summary_text(self) -> str:
        return self.summary.strip()

    @property
    def json_filename(self) -> str:
        return f"{normalize_filename_prefix(self.filename_prefix)}.json"


DOCUMENT_FORMATS = tuple(sorted(DocumentAnalyzer().supported_formats.keys()))
IMAGE_FORMATS = tuple(sorted(ImageMetadataExtractor().supported_formats))
DOCUMENT_MIME_TYPES: Dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword", "application/x-tika-msoffice"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".xls": {"application/vnd.ms-excel", "application/x-tika-msoffice"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    ".ppt": {"application/vnd.ms-powerpoint", "application/x-tika-msoffice"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
    ".odt": {"application/vnd.oasis.opendocument.text", "application/zip"},
    ".ods": {"application/vnd.oasis.opendocument.spreadsheet", "application/zip"},
    ".odp": {"application/vnd.oasis.opendocument.presentation", "application/zip"},
    ".rtf": {"application/rtf", "text/rtf"},
}


def format_summary(title: str, fields: Sequence[tuple[str, Any]]) -> str:
    lines = [title]
    lines.extend(f"- {label}: {value}" for label, value in fields)
    return "\n".join(lines)


def normalize_filename_prefix(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "result"


def usage_error(service_name: str) -> ValueError:
    return ValueError(SERVICE_USAGE[service_name])


def invalid_argument_error() -> ValueError:
    return ValueError(GENERIC_ARGUMENT_ERROR)


def validate_required_text(service_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise usage_error(service_name)
    return normalized


def execute_capability(handler: Callable[..., CommandResult], *args: Any, **kwargs: Any) -> CommandResult:
    try:
        return handler(*args, **kwargs)
    except ValueError:
        raise
    except Exception as exc:
        raise ControlledServiceError(CONTROLLED_TOOL_FAILURE) from exc


def execute_file_capability(handler: Callable[..., CommandResult], *args: Any, **kwargs: Any) -> CommandResult:
    try:
        return handler(*args, **kwargs)
    except FileServiceError:
        raise
    except ValueError as exc:
        raise FileServiceError(str(exc)) from exc
    except Exception as exc:
        raise ControlledServiceError(CONTROLLED_TOOL_FAILURE) from exc


def run_username_lookup(username: str) -> CommandResult:
    searcher = UsernameSearcher(delay=0.2)
    results = searcher.search(username, max_workers=5)
    found_platforms = [item["platform"] for item in results.get("found", [])[:5]]
    platform_summary = ", ".join(found_platforms) if found_platforms else "sin perfiles confirmados"
    summary = format_summary(
        f"Busqueda de username @{results['username']}",
        [
            ("Plataformas revisadas", results["total_checked"]),
            ("Encontrados", len(results["found"])),
            ("No encontrados", len(results["not_found"])),
            ("Perfiles destacados", platform_summary),
        ],
    )
    return CommandResult(summary=summary, payload=results, filename_prefix=f"username_{results['username']}")


def run_email_lookup(email: str) -> CommandResult:
    investigator = EmailOSINT()
    results = investigator.investigate(email, check_breach=False)
    validation = results.get("validation") or {}
    domain = validation.get("domain") or "desconocido"
    provider_type = (validation.get("domain_analysis") or {}).get("provider_type", "unknown")
    summary = format_summary(
        f"Analisis de email {email}",
        [
            ("Valido", "si" if validation.get("is_valid") else "no"),
            ("Dominio", domain),
            ("Tipo de proveedor", provider_type),
            ("Recomendaciones", len(results.get("recommendations", []))),
        ],
    )
    return CommandResult(summary=summary, payload=results, filename_prefix=f"email_{email.replace('@', '_at_')}")


def run_phone_lookup(phone_number: str, region: str = "US") -> CommandResult:
    investigator = PhoneInvestigator()
    results = investigator.investigate(phone_number, region)
    parsing = results.get("parsing") or {}
    summary = format_summary(
        f"Analisis de telefono {phone_number}",
        [
            ("Valido", "si" if parsing.get("is_valid") else "no"),
            ("Pais", parsing.get("country") or "desconocido"),
            ("Tipo", parsing.get("number_type") or "desconocido"),
            ("Operadora", parsing.get("carrier") or "sin datos"),
        ],
    )
    digits = "".join(char for char in phone_number if char.isdigit()) or "phone"
    return CommandResult(summary=summary, payload=results, filename_prefix=f"phone_{digits}")


def run_company_lookup(company_name: str, country_code: str | None = None) -> CommandResult:
    researcher = CompanyResearcher()
    results = researcher.search_company(company_name, country_code)
    links = list(results.get("direct_links", {}).keys())[:3]
    links_summary = ", ".join(links) if links else "sin fuentes globales"
    summary = format_summary(
        f"Investigacion de empresa {company_name}",
        [
            ("Pais", country_code or "global"),
            ("Registros sugeridos", len(results.get("registers_to_check", []))),
            ("Fuentes globales", links_summary),
            ("Recomendaciones", len(results.get("recommendations", []))),
        ],
    )
    safe_name = company_name.strip().replace(" ", "_") or "company"
    return CommandResult(summary=summary, payload=results, filename_prefix=f"company_{safe_name}")


def run_geo_lookup(coords_input: str) -> CommandResult:
    helper = GeolocationHelper()
    coords = helper.parse_coordinates(coords_input)
    if coords is None:
        raise ValueError("No se pudieron parsear las coordenadas. Usa formato 'lat, lon'.")

    results = helper.analyze_coordinates(coords.latitude, coords.longitude)
    location_info = results.get("location_info") or {}
    summary = format_summary(
        f"Analisis geografico {coords.latitude:.6f}, {coords.longitude:.6f}",
        [
            (
                "Hemisferio",
                f"{location_info.get('hemisphere_ns', 'N/A')} / {location_info.get('hemisphere_ew', 'N/A')}",
            ),
            ("Zona horaria aprox", location_info.get("approx_timezone", "N/A")),
            ("Direccion aprox", location_info.get("approx_address", "N/A")),
        ],
    )
    filename = f"geo_{coords.latitude}_{coords.longitude}".replace(".", "_")
    return CommandResult(summary=summary, payload=results, filename_prefix=filename)


def run_social_lookup(username: str) -> CommandResult:
    analyzer = SocialMediaAnalyzer(delay=0.2)
    results = analyzer.cross_reference(username)
    summary = format_summary(
        f"Analisis social @{results['username']}",
        [
            ("Plataformas revisadas", len(results.get("platforms_checked", []))),
            ("Perfiles encontrados", len(results.get("profiles_found", []))),
            ("No encontrados", len(results.get("profiles_not_found", []))),
            ("Cross-references", len(results.get("cross_references", []))),
        ],
    )
    return CommandResult(summary=summary, payload=results, filename_prefix=f"social_{results['username']}")


def run_breach_lookup(value: str) -> CommandResult:
    checker = BreachChecker()
    if "@" in value:
        results = checker.analyze_exposure_risk(value)
        summary = format_summary(
            f"Analisis de brechas {value}",
            [
                ("Tipo", "email"),
                ("Nivel de riesgo", results.get("risk_level", "unknown")),
                ("Factores de riesgo", len(results.get("risk_factors", []))),
                ("Recomendaciones", len(results.get("recommendations", []))),
            ],
        )
        safe_value = value.replace("@", "_at_")
    else:
        results = checker.check_username_breach(value)
        summary = format_summary(
            f"Analisis de brechas {value}",
            [
                ("Tipo", "username"),
                ("Fuentes revisadas", len(results.get("sources_checked", []))),
                ("Hallazgos potenciales", len(results.get("potential_breaches", []))),
                ("Recomendaciones", len(results.get("recommendations", []))),
            ],
        )
        safe_value = value

    return CommandResult(summary=summary, payload=results, filename_prefix=f"breach_{safe_value}")


def is_supported_document(filename: str) -> bool:
    return Path(filename).suffix.lower() in DOCUMENT_FORMATS


def is_supported_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_FORMATS


def is_allowed_document_mime_type(file_name: str, mime_type: str | None) -> bool:
    if not mime_type:
        return True
    allowed = DOCUMENT_MIME_TYPES.get(Path(file_name).suffix.lower())
    if not allowed:
        return True
    return mime_type in allowed


def validate_file_upload(
    service_name: str,
    original_name: str,
    *,
    file_size: int | None = None,
    max_upload_size_bytes: int | None = None,
    mime_type: str | None = None,
) -> None:
    if service_name == "document":
        if not is_supported_document(original_name):
            raise FileServiceError(UNSUPPORTED_DOCUMENT_ERROR)
        if not is_allowed_document_mime_type(original_name, mime_type):
            raise FileServiceError("Tipo MIME de documento no soportado para este archivo.")
    elif service_name == "image":
        if not is_supported_image(original_name):
            raise FileServiceError(UNSUPPORTED_IMAGE_ERROR)
    else:
        raise FileServiceError(f"Unsupported file service: {service_name}")

    if file_size is not None and file_size <= 0:
        raise FileServiceError(EMPTY_UPLOAD_ERROR)
    if max_upload_size_bytes is not None and file_size is not None and file_size > max_upload_size_bytes:
        raise FileServiceError(f"Archivo demasiado grande. Limite actual: {max_upload_size_bytes} bytes.")


def validate_file_signature(service_name: str, temp_path: str, original_name: str) -> None:
    with open(temp_path, "rb") as handle:
        header = handle.read(16)

    if not header:
        raise FileServiceError(EMPTY_UPLOAD_ERROR)

    if service_name == "document" and not is_valid_document_signature(original_name, header):
        raise FileServiceError(CORRUPTED_UPLOAD_ERROR)
    if service_name == "image" and not is_valid_image_signature(original_name, header):
        raise FileServiceError(CORRUPTED_UPLOAD_ERROR)


def is_valid_document_signature(file_name: str, header: bytes) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return header.startswith(b"%PDF")
    if suffix in {".doc", ".xls", ".ppt"}:
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if suffix in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
        return header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if suffix == ".rtf":
        return header.startswith(b"{\\rtf")
    return True


def is_valid_image_signature(file_name: str, header: bytes) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".bmp":
        return header.startswith(b"BM")
    if suffix in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if suffix == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return True


def run_document_lookup(file_path: str, original_name: str) -> CommandResult:
    if not is_supported_document(original_name):
        raise ValueError("Formato de documento no soportado. Envia PDF u Office/OpenDocument.")

    analyzer = DocumentAnalyzer()
    with contextlib.redirect_stdout(io.StringIO()):
        results = analyzer.analyze_document(file_path)

    file_type = results.get("file_type") or Path(original_name).suffix.lower().lstrip(".").upper()
    file_stats = results.get("file_stats") or {}
    summary = format_summary(
        f"Analisis de documento {original_name}",
        [
            ("Tipo", file_type or "desconocido"),
            ("Tamano bytes", file_stats.get("size_bytes") or "N/A"),
            ("Modificado", file_stats.get("modified") or "N/A"),
            ("Error", results.get("error") or "sin errores"),
        ],
    )
    safe_name = Path(original_name).stem.replace(" ", "_") or "document"
    return CommandResult(summary=summary, payload=results, filename_prefix=f"document_{safe_name}")


def run_image_lookup(file_path: str, original_name: str) -> CommandResult:
    if not is_supported_image(original_name):
        raise ValueError("Formato de imagen no soportado.")

    extractor = ImageMetadataExtractor()
    with contextlib.redirect_stdout(io.StringIO()):
        results = extractor.analyze_image(file_path)

    gps_info = results.get("gps_info") or {}
    privacy = results.get("privacy_analysis") or {}
    summary = format_summary(
        f"Analisis de imagen {original_name}",
        [
            ("Formato", results.get("format") or results.get("file_type") or "desconocido"),
            ("Dimensiones", f"{results.get('width', '?')}x{results.get('height', '?')}"),
            ("GPS", "si" if gps_info else "no"),
            ("Riesgos privacidad", privacy.get("risk_count", 0)),
        ],
    )
    safe_name = Path(original_name).stem.replace(" ", "_") or "image"
    return CommandResult(summary=summary, payload=results, filename_prefix=f"image_{safe_name}")


SERVICE_HANDLERS: Dict[str, Callable[..., CommandResult]] = {
    "username": run_username_lookup,
    "email": run_email_lookup,
    "phone": run_phone_lookup,
    "company": run_company_lookup,
    "geo": run_geo_lookup,
    "social": run_social_lookup,
    "breach": run_breach_lookup,
}

FILE_HANDLERS: Dict[str, Callable[[str, str], CommandResult]] = {
    "document": run_document_lookup,
    "image": run_image_lookup,
}


def dispatch_service(service_name: str, args: Sequence[str]) -> CommandResult:
    normalized_args = [arg.strip() for arg in args if arg and arg.strip()]
    with contextlib.redirect_stdout(io.StringIO()):
        if service_name == "phone":
            return dispatch_phone_service(normalized_args)
        if service_name == "company":
            return dispatch_company_service(normalized_args)
        if service_name in {"username", "email", "geo", "social", "breach"}:
            value = validate_required_text(service_name, " ".join(normalized_args))
            return dispatch_value_service(service_name, value)
    raise ValueError(f"Unsupported service: {service_name}")


def dispatch_file_service(
    service_name: str,
    file_path: str,
    original_name: str,
    *,
    file_size: int | None = None,
    max_upload_size_bytes: int | None = None,
    mime_type: str | None = None,
) -> CommandResult:
    try:
        handler = FILE_HANDLERS[service_name]
    except KeyError as exc:
        raise FileServiceError(f"Unsupported file service: {service_name}") from exc
    validate_file_upload(
        service_name,
        original_name,
        file_size=file_size,
        max_upload_size_bytes=max_upload_size_bytes,
        mime_type=mime_type,
    )
    validate_file_signature(service_name, file_path, original_name)
    return execute_file_capability(handler, file_path, original_name)


def dispatch_phone_service(args: Sequence[str]) -> CommandResult:
    region = "US"
    phone_parts = list(args)
    if len(phone_parts) >= 2 and phone_parts[0] == "--region":
        region = phone_parts[1].upper()
        phone_parts = phone_parts[2:]
    elif phone_parts and phone_parts[0].startswith("--"):
        raise usage_error("phone")
    if any(part.startswith("--") for part in phone_parts):
        raise usage_error("phone")
    if not phone_parts:
        raise usage_error("phone")
    return execute_capability(run_phone_lookup, " ".join(phone_parts), region=region)


def dispatch_company_service(args: Sequence[str]) -> CommandResult:
    country_code = None
    company_parts = list(args)
    if len(company_parts) >= 2 and company_parts[0] == "--country":
        country_code = company_parts[1].upper()
        company_parts = company_parts[2:]
    elif company_parts and company_parts[0].startswith("--"):
        raise usage_error("company")
    if any(part.startswith("--") for part in company_parts):
        raise usage_error("company")
    if not company_parts:
        raise usage_error("company")
    return execute_capability(run_company_lookup, " ".join(company_parts), country_code=country_code)


def dispatch_value_service(service_name: str, value: str) -> CommandResult:
    if service_name == "email" and not EMAIL_PATTERN.match(value):
        raise invalid_argument_error()
    if service_name == "geo" and "," not in value:
        raise invalid_argument_error()
    return execute_capability(SERVICE_HANDLERS[service_name], value)
