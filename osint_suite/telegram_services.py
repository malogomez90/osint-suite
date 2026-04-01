"""
Servicios de aplicación para el bot de Telegram.

Los handlers del bot deben delegar aquí y mantener la lógica OSINT dentro de
las herramientas existentes del paquete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from .company_research import CompanyResearcher
from .email_osint import EmailOSINT
from .geolocation_helper import GeolocationHelper
from .phone_investigator import PhoneInvestigator
from .username_search import UsernameSearcher


@dataclass
class CommandResult:
    summary: str
    payload: Dict[str, Any]
    filename_prefix: str


def run_username_lookup(username: str) -> CommandResult:
    searcher = UsernameSearcher(delay=0.2)
    results = searcher.search(username, max_workers=5)
    found_platforms = [item["platform"] for item in results.get("found", [])[:5]]
    platform_summary = ", ".join(found_platforms) if found_platforms else "sin perfiles confirmados"
    summary = (
        f"Busqueda de username @{results['username']}\n"
        f"Plataformas revisadas: {results['total_checked']}\n"
        f"Encontrados: {len(results['found'])}\n"
        f"No encontrados: {len(results['not_found'])}\n"
        f"Perfiles destacados: {platform_summary}"
    )
    return CommandResult(summary=summary, payload=results, filename_prefix=f"username_{results['username']}")


def run_email_lookup(email: str) -> CommandResult:
    investigator = EmailOSINT()
    results = investigator.investigate(email, check_breach=False)
    validation = results.get("validation") or {}
    domain = validation.get("domain") or "desconocido"
    provider_type = (validation.get("domain_analysis") or {}).get("provider_type", "unknown")
    summary = (
        f"Analisis de email {email}\n"
        f"Valido: {'si' if validation.get('is_valid') else 'no'}\n"
        f"Dominio: {domain}\n"
        f"Tipo de proveedor: {provider_type}\n"
        f"Recomendaciones: {len(results.get('recommendations', []))}"
    )
    return CommandResult(summary=summary, payload=results, filename_prefix=f"email_{email.replace('@', '_at_')}")


def run_phone_lookup(phone_number: str, region: str = "US") -> CommandResult:
    investigator = PhoneInvestigator()
    results = investigator.investigate(phone_number, region)
    parsing = results.get("parsing") or {}
    summary = (
        f"Analisis de telefono {phone_number}\n"
        f"Valido: {'si' if parsing.get('is_valid') else 'no'}\n"
        f"Pais: {parsing.get('country') or 'desconocido'}\n"
        f"Tipo: {parsing.get('number_type') or 'desconocido'}\n"
        f"Operadora: {parsing.get('carrier') or 'sin datos'}"
    )
    digits = "".join(char for char in phone_number if char.isdigit()) or "phone"
    return CommandResult(summary=summary, payload=results, filename_prefix=f"phone_{digits}")


def run_company_lookup(company_name: str, country_code: str | None = None) -> CommandResult:
    researcher = CompanyResearcher()
    results = researcher.search_company(company_name, country_code)
    links = list(results.get("direct_links", {}).keys())[:3]
    links_summary = ", ".join(links) if links else "sin fuentes globales"
    summary = (
        f"Investigacion de empresa {company_name}\n"
        f"Pais: {country_code or 'global'}\n"
        f"Registros sugeridos: {len(results.get('registers_to_check', []))}\n"
        f"Fuentes globales: {links_summary}\n"
        f"Recomendaciones: {len(results.get('recommendations', []))}"
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
    summary = (
        f"Analisis geografico {coords.latitude:.6f}, {coords.longitude:.6f}\n"
        f"Hemisferio: {location_info.get('hemisphere_ns', 'N/A')} / {location_info.get('hemisphere_ew', 'N/A')}\n"
        f"Zona horaria aprox: {location_info.get('approx_timezone', 'N/A')}\n"
        f"Direccion aprox: {location_info.get('approx_address', 'N/A')}"
    )
    filename = f"geo_{coords.latitude}_{coords.longitude}".replace(".", "_")
    return CommandResult(summary=summary, payload=results, filename_prefix=filename)


SERVICE_HANDLERS: Dict[str, Callable[..., CommandResult]] = {
    "username": run_username_lookup,
    "email": run_email_lookup,
    "phone": run_phone_lookup,
    "company": run_company_lookup,
    "geo": run_geo_lookup,
}
