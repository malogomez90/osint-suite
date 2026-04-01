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
from .username_search import UsernameSearcher


@dataclass
class CommandResult:
    summary: str
    payload: Dict[str, Any]
    filename_prefix: str


DOCUMENT_FORMATS = tuple(sorted(DocumentAnalyzer().supported_formats.keys()))
IMAGE_FORMATS = tuple(sorted(ImageMetadataExtractor().supported_formats))


def format_summary(title: str, fields: Sequence[tuple[str, Any]]) -> str:
    lines = [title]
    lines.extend(f"- {label}: {value}" for label, value in fields)
    return "\n".join(lines)


def normalize_filename_prefix(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "result"


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


def is_supported_document(filename: str) -> bool:
    return Path(filename).suffix.lower() in DOCUMENT_FORMATS


def is_supported_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_FORMATS


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
}

FILE_HANDLERS: Dict[str, Callable[[str, str], CommandResult]] = {
    "document": run_document_lookup,
    "image": run_image_lookup,
}


def dispatch_service(service_name: str, args: Sequence[str]) -> CommandResult:
    normalized_args = [arg.strip() for arg in args if arg and arg.strip()]
    if service_name == "phone":
        return dispatch_phone_service(normalized_args)
    if service_name == "company":
        return dispatch_company_service(normalized_args)
    if service_name in {"username", "email", "geo"}:
        return SERVICE_HANDLERS[service_name](" ".join(normalized_args).strip())
    raise ValueError(f"Unsupported service: {service_name}")


def dispatch_file_service(service_name: str, file_path: str, original_name: str) -> CommandResult:
    try:
        handler = FILE_HANDLERS[service_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported file service: {service_name}") from exc
    return handler(file_path, original_name)


def dispatch_phone_service(args: Sequence[str]) -> CommandResult:
    region = "US"
    phone_parts = list(args)
    if len(phone_parts) >= 2 and phone_parts[0] == "--region":
        region = phone_parts[1].upper()
        phone_parts = phone_parts[2:]
    if not phone_parts:
        raise ValueError("Falta el numero de telefono.")
    return run_phone_lookup(" ".join(phone_parts), region=region)


def dispatch_company_service(args: Sequence[str]) -> CommandResult:
    country_code = None
    company_parts = list(args)
    if len(company_parts) >= 2 and company_parts[0] == "--country":
        country_code = company_parts[1].upper()
        company_parts = company_parts[2:]
    if not company_parts:
        raise ValueError("Falta el nombre de la empresa.")
    return run_company_lookup(" ".join(company_parts), country_code=country_code)
