"""Create EHDS-aligned copies of local Patient Summary FHIR Bundles.

The script keeps source bundles unchanged. It adds explicit empty Composition
sections only where an eHDSI "at least present" section is absent and records a
short human-readable alignment report.
"""

from __future__ import annotations

import argparse
import os
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "Test_documents"
OUTPUT_DIR = ROOT / "EHDS_aligned_FHIR_resouces"
REPORT_PATH = OUTPUT_DIR / "EHDS_alignment_report.md"
DEFAULT_CTS_ENV_PATH = Path(r"C:\Users\duncanfalconer\VS_Code_Projects\CTS_testing\.env")
DEFAULT_NMPC_ENV_PATH = Path(r"C:\Users\duncanfalconer\VS_Code_Projects\NMPC_Testing\.env")


SYSTEM_VALUESETS = {
    "http://snomed.info/sct": "http://snomed.info/sct?fhir_vs",
    "http://loinc.org": "http://loinc.org/vs",
}


CODEABLE_FIELD_PREFERRED_SYSTEMS = {
    "code": {
        "AllergyIntolerance": ["http://snomed.info/sct"],
        "Condition": ["http://snomed.info/sct"],
        "Procedure": ["http://snomed.info/sct"],
        "Observation": ["http://loinc.org", "http://snomed.info/sct"],
    },
    "medicationCodeableConcept": {
        "MedicationStatement": ["http://snomed.info/sct"],
    },
    "vaccineCode": {
        "Immunization": ["http://snomed.info/sct"],
    },
    "valueCodeableConcept": {
        "Observation": ["http://snomed.info/sct"],
    },
}


KNOWN_CODEABLE_FIELDS = set(CODEABLE_FIELD_PREFERRED_SYSTEMS)


NMPC_SNOMED_SYSTEM = "http://snomed.info/sct"
NMPC_PRODUCT_VALUESET = "http://snomed.info/sct?fhir_vs=refset/660401000220107"
NMPC_MAPS = {
    "hpra": "690021000220108",
    "pcrs": "680461000220105",
    "atc": "680441000220106",
}
NMPC_EXTERNAL_SYSTEMS = {
    "hpra": "https://nmpc.hse.ie/HPRA",
    "pcrs": "https://nmpc.hse.ie/PCRS",
    "atc": "http://www.whocc.no/atc",
}


EHDI_AT_LEAST_SECTIONS: dict[str, dict[str, str]] = {
    "Medication Summary": {
        "loinc": "10160-0",
        "display": "History of Medication use Narrative",
        "ehdsi_name": "eHDSI Medication Summary",
    },
    "Allergies and Intolerances": {
        "loinc": "48765-2",
        "display": "Allergies and adverse reactions Document",
        "ehdsi_name": "eHDSI Allergies and Other Adverse Reactions",
    },
    "History of Procedures": {
        "loinc": "47519-4",
        "display": "History of Procedures Document",
        "ehdsi_name": "eHDSI List of Surgeries",
    },
    "Problem List": {
        "loinc": "11450-4",
        "display": "Problem list - Reported",
        "ehdsi_name": "eHDSI Active Problems",
    },
    "Medical Devices": {
        "loinc": "46264-8",
        "display": "History of medical device use",
        "ehdsi_name": "eHDSI Medical Devices",
    },
}


OPTIONAL_PATIENT_SUMMARY_SECTIONS: dict[str, dict[str, str]] = {
    "History of Past Illness": {
        "loinc": "11348-0",
        "display": "History of Past illness note",
    },
    "History of Immunizations": {
        "loinc": "11369-6",
        "display": "History of Immunization note",
    },
    "Vital Signs": {
        "loinc": "8716-3",
        "display": "Vital signs note",
    },
    "Laboratory Results": {
        "loinc": "30954-2",
        "display": "Relevant diagnostic tests/laboratory data note",
    },
    "Pregnancy History": {
        "loinc": "10162-6",
        "display": "History of pregnancies Narrative",
    },
    "Functional Status": {
        "loinc": "47420-5",
        "display": "Functional status assessment note",
    },
    "Social History": {
        "loinc": "29762-2",
        "display": "Social history note",
    },
    "Advance Directives": {
        "loinc": "42348-3",
        "display": "Advance healthcare directives",
    },
}


def load_bundle(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_bundle(path: Path, bundle: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class CTSTerminologyClient:
    """Minimal HSE CTS FHIR client using OAuth2 client credentials."""

    def __init__(self) -> None:
        self.base_url = os.getenv("CTS_API_BASE_URL", "").rstrip("/")
        self.token_url = os.getenv("CTS_TOKEN_URL", "")
        self.client_id = os.getenv("CTS_CLIENT_ID", "")
        self.client_secret = os.getenv("CTS_CLIENT_SECRET", "")
        self.timeout = int(os.getenv("CTS_TIMEOUT_SECONDS", "30"))
        self._access_token: str | None = None
        self.enabled = all(
            [self.base_url, self.token_url, self.client_id, self.client_secret]
        )
        self.status = (
            "enabled"
            if self.enabled
            else "disabled: CTS_API_BASE_URL, CTS_TOKEN_URL, CTS_CLIENT_ID, or CTS_CLIENT_SECRET missing"
        )
        self.failure_count = 0
        self.last_error: str | None = None
        self.lookup_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
        self.expand_cache: dict[tuple[str, str, int], list[dict[str, Any]]] = {}

    def _disable_after_failure(self, exc: Exception) -> None:
        self.failure_count += 1
        self.last_error = str(exc)[:200]
        self.enabled = False
        self.status = f"disabled after CTS request failure: {self.last_error}"

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{parse.urlencode(params)}"

        http_request = request.Request(
            url,
            data=data,
            method=method,
            headers=headers or {},
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def _token(self) -> str:
        if self._access_token:
            return self._access_token

        form_data = parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        token_response = self._request_json(
            "POST",
            self.token_url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._access_token = token_response["access_token"]
        return self._access_token

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/fhir+json",
        }
        return self._request_json(
            "GET", f"{self.base_url}{path}", params=params, headers=headers
        )

    def lookup_code(self, system: str, code: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        cache_key = (system, code)
        if cache_key in self.lookup_cache:
            return self.lookup_cache[cache_key]

        try:
            result = self.get(
                "/CodeSystem/$lookup", {"system": system, "code": code}
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                result = None
            else:
                self._disable_after_failure(exc)
                result = None
        except Exception as exc:
            self._disable_after_failure(exc)
            result = None

        self.lookup_cache[cache_key] = result
        return result

    def expand_valueset(
        self, valueset_url: str, filter_text: str, count: int = 10
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        cache_key = (valueset_url, filter_text.casefold(), count)
        if cache_key in self.expand_cache:
            return self.expand_cache[cache_key]

        try:
            result = self.get(
                "/ValueSet/$expand",
                {"url": valueset_url, "filter": filter_text, "count": count},
            )
            contains = result.get("expansion", {}).get("contains", [])
        except error.HTTPError as exc:
            if exc.code == 404:
                contains = []
            else:
                self._disable_after_failure(exc)
                contains = []
        except Exception as exc:
            self._disable_after_failure(exc)
            contains = []

        self.expand_cache[cache_key] = contains
        return contains


class NMPCClient:
    """Minimal Irish NMPC FHIR API client using OAuth2 client credentials."""

    def __init__(self) -> None:
        self.base_url = os.getenv("NMPC_API_BASE_URL", "").rstrip("/")
        self.auth_url = os.getenv("NMPC_AUTH_URL", "")
        self.client_id = os.getenv("NMPC_CLIENT_ID", "")
        self.client_secret = os.getenv("NMPC_CLIENT_SECRET", "")
        self.timeout = int(os.getenv("NMPC_REQUEST_TIMEOUT", "30"))
        self._access_token: str | None = None
        self.enabled = all(
            [self.base_url, self.auth_url, self.client_id, self.client_secret]
        )
        self.status = (
            "enabled"
            if self.enabled
            else "disabled: NMPC_API_BASE_URL, NMPC_AUTH_URL, NMPC_CLIENT_ID, or NMPC_CLIENT_SECRET missing"
        )
        self.failure_count = 0
        self.last_error: str | None = None
        self.lookup_cache: dict[str, dict[str, Any] | None] = {}
        self.expand_cache: dict[tuple[str, str | None, int, int], dict[str, Any]] = {}
        self.translate_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def _disable_after_failure(self, exc: Exception) -> None:
        self.failure_count += 1
        self.last_error = str(exc)[:200]
        self.enabled = False
        self.status = f"disabled after NMPC request failure: {self.last_error}"

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{parse.urlencode(params)}"

        http_request = request.Request(
            url,
            data=data,
            method=method,
            headers=headers or {},
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def _token(self) -> str:
        if self._access_token:
            return self._access_token

        form_data = parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        token_response = self._request_json(
            "POST",
            self.auth_url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._access_token = token_response["access_token"]
        return self._access_token

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/fhir+json",
        }
        return self._request_json(
            "GET", f"{self.base_url}{path}", params=params, headers=headers
        )

    def lookup_code(self, code: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        if code in self.lookup_cache:
            return self.lookup_cache[code]

        try:
            result = self.get(
                "/CodeSystem/$lookup",
                {"system": NMPC_SNOMED_SYSTEM, "code": code},
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                result = None
            else:
                self._disable_after_failure(exc)
                result = None
        except Exception as exc:
            self._disable_after_failure(exc)
            result = None

        self.lookup_cache[code] = result
        return result

    def expand_valueset(
        self,
        valueset_url: str,
        filter_text: str | None = None,
        count: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"total": 0, "results": []}

        cache_key = (valueset_url, filter_text, count, offset)
        if cache_key in self.expand_cache:
            return self.expand_cache[cache_key]

        params: dict[str, Any] = {
            "url": valueset_url,
            "count": count,
            "offset": offset,
        }
        if filter_text:
            params["filter"] = filter_text

        try:
            data = self.get("/ValueSet/$expand", params)
            expansion = data.get("expansion", {})
            contains = expansion.get("contains", [])
            result = {
                "total": expansion.get("total", len(contains)),
                "results": [
                    {
                        "system": item.get("system") or NMPC_SNOMED_SYSTEM,
                        "code": item.get("code"),
                        "display": item.get("display"),
                    }
                    for item in contains
                    if item.get("code")
                ],
            }
        except error.HTTPError as exc:
            if exc.code == 404:
                result = {"total": 0, "results": []}
            else:
                self._disable_after_failure(exc)
                result = {"total": 0, "results": []}
        except Exception as exc:
            self._disable_after_failure(exc)
            result = {"total": 0, "results": []}

        self.expand_cache[cache_key] = result
        return result

    def find_products_by_text(self, text: str, count: int = 10) -> dict[str, Any]:
        return self.expand_valueset(NMPC_PRODUCT_VALUESET, text, count=count)

    def find_products_by_map_target(
        self, map_key: str, target_code: str, count: int = 10
    ) -> dict[str, Any]:
        map_id = NMPC_MAPS[map_key]
        ecl = f'(^ {map_id} {{{{ M mapTarget="{target_code}" }}}} AND ^660401000220107 )'
        valueset_url = f"{NMPC_SNOMED_SYSTEM}?fhir_vs=ecl/{parse.quote(ecl, safe='')}"
        return self.expand_valueset(valueset_url, count=count)

    def translate_code(self, code: str, map_key: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        cache_key = (code, map_key)
        if cache_key in self.translate_cache:
            return self.translate_cache[cache_key]

        map_id = NMPC_MAPS[map_key]
        try:
            data = self.get(
                "/ConceptMap/$translate",
                {
                    "url": f"{NMPC_SNOMED_SYSTEM}?fhir_cm={map_id}",
                    "code": code,
                    "system": NMPC_SNOMED_SYSTEM,
                },
            )
            matches = parse_translate_matches(data)
        except error.HTTPError as exc:
            if exc.code == 404:
                matches = []
            else:
                self._disable_after_failure(exc)
                matches = []
        except Exception as exc:
            self._disable_after_failure(exc)
            matches = []

        self.translate_cache[cache_key] = matches
        return matches


def parameters_to_dict(parameters_resource: dict[str, Any] | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not parameters_resource:
        return values

    for parameter in parameters_resource.get("parameter", []):
        name = parameter.get("name")
        if not name:
            continue

        for value_key in ("valueString", "valueCode", "valueUri", "valueBoolean"):
            if value_key in parameter:
                values[name] = parameter[value_key]
                break

    return values


def parse_translate_matches(parameters_resource: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for parameter in parameters_resource.get("parameter", []):
        if parameter.get("name") != "match":
            continue

        match: dict[str, Any] = {}
        for part in parameter.get("part", []):
            part_name = part.get("name")
            if part_name == "equivalence":
                match["equivalence"] = part.get("valueCode")
            elif part_name == "concept":
                coding = part.get("valueCoding", {})
                if coding.get("code"):
                    match.update(
                        {
                            "system": coding.get("system"),
                            "code": coding.get("code"),
                            "display": coding.get("display"),
                        }
                    )
        if match.get("code"):
            matches.append(match)
    return matches


def normalize_term(value: str) -> str:
    return " ".join(value.casefold().replace(",", " ").split())


def add_cts_source_extension(coding: dict[str, Any], operation: str) -> None:
    extension_url = (
        "https://datastandards.hse.ie/fhir/StructureDefinition/cts-enrichment-source"
    )
    extensions = coding.setdefault("extension", [])
    if any(extension.get("url") == extension_url for extension in extensions):
        return

    extensions.append(
        {
            "url": extension_url,
            "extension": [
                {"url": "server", "valueUrl": "https://datastandards.hse.ie/fhir"},
                {"url": "operation", "valueCode": operation},
            ],
        }
    )


def add_nmpc_source_extension(target: dict[str, Any], operation: str) -> None:
    extension_url = "https://nmpc.hse.ie/fhir/StructureDefinition/nmpc-enrichment-source"
    extensions = target.setdefault("extension", [])
    if any(extension.get("url") == extension_url for extension in extensions):
        return

    extensions.append(
        {
            "url": extension_url,
            "extension": [
                {"url": "server", "valueUrl": "https://nmpc.hse.ie/production1/fhir"},
                {"url": "operation", "valueCode": operation},
            ],
        }
    )


def add_nmpc_candidate_extension(
    codeable_concept: dict[str, Any],
    source_system: str,
    source_code: str,
    total: int,
    candidates: list[dict[str, Any]],
) -> None:
    extension_url = "https://nmpc.hse.ie/fhir/StructureDefinition/nmpc-candidate-match"
    extensions = codeable_concept.setdefault("extension", [])
    if any(
        extension.get("url") == extension_url
        and any(
            part.get("url") == "sourceCode" and part.get("valueCode") == source_code
            for part in extension.get("extension", [])
        )
        for extension in extensions
    ):
        return

    candidate_parts = []
    for candidate in candidates[:5]:
        candidate_parts.append(
            {
                "url": "candidate",
                "extension": [
                    {"url": "system", "valueUri": candidate.get("system") or NMPC_SNOMED_SYSTEM},
                    {"url": "code", "valueCode": candidate.get("code")},
                    {"url": "display", "valueString": candidate.get("display") or ""},
                ],
            }
        )

    extensions.append(
        {
            "url": extension_url,
            "extension": [
                {"url": "sourceSystem", "valueUri": source_system},
                {"url": "sourceCode", "valueCode": source_code},
                {"url": "totalCandidates", "valueInteger": total},
                *candidate_parts,
            ],
        }
    )


def coding_display_from_cts(
    client: CTSTerminologyClient, coding: dict[str, Any]
) -> str | None:
    system = coding.get("system")
    code = coding.get("code")
    if not system or not code:
        return None

    lookup = parameters_to_dict(client.lookup_code(system, code))
    display = lookup.get("display") or lookup.get("name")
    return str(display) if display else None


def preferred_systems_for(
    resource_type: str | None, field_name: str
) -> list[str]:
    return CODEABLE_FIELD_PREFERRED_SYSTEMS.get(field_name, {}).get(
        resource_type or "", []
    )


def exact_candidate_from_cts(
    client: CTSTerminologyClient, text: str, systems: list[str]
) -> dict[str, Any] | None:
    normalized_text = normalize_term(text)
    exact_matches: list[dict[str, Any]] = []

    for system in systems:
        valueset_url = SYSTEM_VALUESETS.get(system)
        if not valueset_url:
            continue

        for candidate in client.expand_valueset(valueset_url, text, count=10):
            candidate_system = candidate.get("system") or system
            candidate_code = candidate.get("code")
            candidate_display = candidate.get("display")

            if not candidate_code or not candidate_display:
                continue

            if normalize_term(candidate_display) == normalized_text:
                exact_matches.append(
                    {
                        "system": candidate_system,
                        "code": candidate_code,
                        "display": candidate_display,
                    }
                )

    unique_matches = {
        (match["system"], match["code"], match["display"]): match
        for match in exact_matches
    }
    if len(unique_matches) == 1:
        return next(iter(unique_matches.values()))

    return None


def enrich_terminology(
    bundle: dict[str, Any], client: CTSTerminologyClient
) -> tuple[list[str], dict[str, int]]:
    changes: list[str] = []
    stats = Counter(
        {
            "lookups_attempted": 0,
            "displays_added": 0,
            "searches_attempted": 0,
            "codings_added": 0,
            "unresolved_text_concepts": 0,
        }
    )

    if not client.enabled:
        return [f"CTS terminology enrichment skipped ({client.status})."], dict(stats)

    def walk(value: Any, path: str, resource_type: str | None = None) -> None:
        if not client.enabled:
            return

        if isinstance(value, dict):
            current_resource_type = resource_type
            if isinstance(value.get("resourceType"), str):
                current_resource_type = value["resourceType"]

            if isinstance(value.get("coding"), list):
                for index, coding in enumerate(value["coding"]):
                    if not isinstance(coding, dict):
                        continue
                    if coding.get("system") and coding.get("code") and not coding.get(
                        "display"
                    ):
                        stats["lookups_attempted"] += 1
                        display = coding_display_from_cts(client, coding)
                        if display:
                            coding["display"] = display
                            add_cts_source_extension(coding, "CodeSystem/$lookup")
                            stats["displays_added"] += 1
                            changes.append(
                                f"Added display '{display}' to {path}/coding[{index}] "
                                f"({coding['system']}|{coding['code']}) using CTS lookup."
                            )

            field_name = path.rsplit("/", 1)[-1]
            text = value.get("text")
            codings = value.get("coding")
            has_coding = isinstance(codings, list) and bool(codings)
            can_search = (
                isinstance(text, str)
                and text.strip()
                and not has_coding
                and (field_name in KNOWN_CODEABLE_FIELDS or "coding" in value)
            )
            if can_search:
                systems = preferred_systems_for(current_resource_type, field_name)
                if systems:
                    stats["searches_attempted"] += 1
                    candidate = exact_candidate_from_cts(client, text, systems)
                    if candidate:
                        coding = {
                            "system": candidate["system"],
                            "code": candidate["code"],
                            "display": candidate["display"],
                        }
                        add_cts_source_extension(coding, "ValueSet/$expand")
                        value["coding"] = [coding]
                        stats["codings_added"] += 1
                        changes.append(
                            f"Added {candidate['system']}|{candidate['code']} to {path} "
                            f"from exact CTS match on text '{text}'."
                        )
                    else:
                        stats["unresolved_text_concepts"] += 1

            for key, child in value.items():
                walk(child, f"{path}/{key}", current_resource_type)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", resource_type)

    walk(bundle, "")
    if client.failure_count:
        changes.append(f"CTS terminology enrichment stopped early ({client.status}).")
    elif not changes:
        changes.append("CTS terminology enrichment ran, but no safe coding changes were found.")

    return changes, dict(stats)


def coding_exists(codeable_concept: dict[str, Any], system: str, code: str) -> bool:
    for coding in codeable_concept.get("coding", []):
        if coding.get("system") == system and coding.get("code") == code:
            return True
    return False


def medication_statement_context(resource: dict[str, Any]) -> str:
    identifier = resource.get("id") or "unknown-id"
    effective = resource.get("effectiveDateTime") or resource.get("effectivePeriod", "")
    return f"MedicationStatement/{identifier}" + (f" ({effective})" if effective else "")


def add_nmpc_coding(
    codeable_concept: dict[str, Any],
    candidate: dict[str, Any],
    operation: str,
) -> bool:
    code = candidate.get("code")
    display = candidate.get("display")
    system = candidate.get("system") or NMPC_SNOMED_SYSTEM
    if not code or coding_exists(codeable_concept, system, code):
        return False

    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    add_nmpc_source_extension(coding, operation)
    codeable_concept.setdefault("coding", []).append(coding)
    return True


def add_external_mapping_coding(
    codeable_concept: dict[str, Any],
    map_key: str,
    match: dict[str, Any],
) -> bool:
    code = match.get("code")
    system = match.get("system") or NMPC_EXTERNAL_SYSTEMS.get(map_key)
    if not code or not system or coding_exists(codeable_concept, system, code):
        return False

    coding = {"system": system, "code": code}
    if match.get("display"):
        coding["display"] = match["display"]
    add_nmpc_source_extension(coding, f"ConceptMap/$translate:{map_key}")
    codeable_concept.setdefault("coding", []).append(coding)
    return True


def enrich_medications_with_nmpc(
    bundle: dict[str, Any], client: NMPCClient
) -> tuple[list[str], dict[str, int]]:
    changes: list[str] = []
    stats = Counter(
        {
            "medication_statements_checked": 0,
            "atc_reverse_searches": 0,
            "text_searches": 0,
            "nmpc_codings_added": 0,
            "candidate_extensions_added": 0,
            "mapping_attempts": 0,
            "mapping_codings_added": 0,
            "ambiguous_matches": 0,
            "unresolved_medications": 0,
        }
    )

    if not client.enabled:
        return [f"NMPC medication enrichment skipped ({client.status})."], dict(stats)

    for resource in bundle_resources(bundle):
        if not client.enabled:
            break
        if resource.get("resourceType") != "MedicationStatement":
            continue

        stats["medication_statements_checked"] += 1
        context = medication_statement_context(resource)
        codeable_concept = resource.get("medicationCodeableConcept")
        if not isinstance(codeable_concept, dict):
            stats["unresolved_medications"] += 1
            continue

        codings = [
            coding
            for coding in codeable_concept.get("coding", [])
            if isinstance(coding, dict)
        ]
        existing_nmpc_codes = [
            coding["code"]
            for coding in codings
            if coding.get("system", "").startswith(NMPC_SNOMED_SYSTEM)
            and coding.get("code")
        ]

        if not existing_nmpc_codes:
            candidate_source = None
            candidate_result: dict[str, Any] | None = None
            atc_codes = [
                coding["code"]
                for coding in codings
                if coding.get("system") == "http://www.whocc.no/atc"
                and coding.get("code")
            ]

            for atc_code in atc_codes:
                stats["atc_reverse_searches"] += 1
                candidate_result = client.find_products_by_map_target(
                    "atc", atc_code, count=10
                )
                candidate_source = ("http://www.whocc.no/atc", atc_code)
                if candidate_result.get("results"):
                    break

            if not candidate_result and codeable_concept.get("text"):
                stats["text_searches"] += 1
                candidate_result = client.find_products_by_text(
                    codeable_concept["text"], count=10
                )
                candidate_source = ("text", codeable_concept["text"])

            if candidate_result and candidate_source:
                total = int(candidate_result.get("total") or 0)
                candidates = candidate_result.get("results", [])
                if total == 1 and len(candidates) == 1:
                    if add_nmpc_coding(
                        codeable_concept, candidates[0], "ValueSet/$expand"
                    ):
                        existing_nmpc_codes.append(candidates[0]["code"])
                        stats["nmpc_codings_added"] += 1
                        changes.append(
                            f"Added NMPC coding {candidates[0]['code']} to {context} "
                            f"from {candidate_source[0]}|{candidate_source[1]}."
                        )
                elif candidates:
                    source_system, source_code = candidate_source
                    add_nmpc_candidate_extension(
                        codeable_concept,
                        source_system,
                        source_code,
                        total,
                        candidates,
                    )
                    stats["candidate_extensions_added"] += 1
                    stats["ambiguous_matches"] += 1
                    changes.append(
                        f"Added NMPC candidate extension to {context}: "
                        f"{total} candidates found from {source_system}|{source_code}; "
                        "no asserted NMPC coding added."
                    )
                else:
                    stats["unresolved_medications"] += 1
            else:
                stats["unresolved_medications"] += 1

        for nmpc_code in existing_nmpc_codes:
            for map_key in ("hpra", "pcrs", "atc"):
                stats["mapping_attempts"] += 1
                for match in client.translate_code(nmpc_code, map_key):
                    if add_external_mapping_coding(codeable_concept, map_key, match):
                        stats["mapping_codings_added"] += 1
                        changes.append(
                            f"Added {map_key.upper()} mapping {match.get('code')} "
                            f"to {context} from NMPC code {nmpc_code}."
                        )

    if client.failure_count:
        changes.append(f"NMPC medication enrichment stopped early ({client.status}).")
    elif not changes:
        changes.append("NMPC medication enrichment ran, but no safe medication changes were found.")

    return changes, dict(stats)


def bundle_resources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry.get("resource", {}) for entry in bundle.get("entry", [])]


def find_composition(bundle: dict[str, Any]) -> dict[str, Any] | None:
    for resource in bundle_resources(bundle):
        if resource.get("resourceType") == "Composition":
            return resource
    return None


def section_code(section: dict[str, Any]) -> str | None:
    for coding in section.get("code", {}).get("coding", []):
        if coding.get("system") == "http://loinc.org":
            return coding.get("code")
    return None


def section_title(section: dict[str, Any]) -> str:
    return str(section.get("title") or section_code(section) or "Untitled section")


def empty_section(title: str, details: dict[str, str]) -> dict[str, Any]:
    return {
        "title": title,
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": details["loinc"],
                    "display": details["display"],
                }
            ]
        },
        "text": {
            "status": "additional",
            "div": (
                "<div xmlns=\"http://www.w3.org/1999/xhtml\">"
                f"<p>No {title.lower()} information was available in the source bundle.</p>"
                "</div>"
            ),
        },
        "emptyReason": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason",
                    "code": "unavailable",
                    "display": "Unavailable",
                }
            ],
            "text": "No information available in source bundle",
        },
    }


def uuid_reference_gaps(bundle: dict[str, Any]) -> list[str]:
    full_urls = {entry.get("fullUrl") for entry in bundle.get("entry", [])}
    references: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("reference")
            if isinstance(reference, str) and reference.startswith("urn:uuid:"):
                references.add(reference)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(bundle)
    return sorted(reference for reference in references if reference not in full_urls)


def analyse_bundle(path: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    resources = bundle_resources(bundle)
    composition = find_composition(bundle)
    sections = composition.get("section", []) if composition else []
    present_codes = {section_code(section) for section in sections}
    present_titles = {section_title(section) for section in sections}

    missing_required = [
        title
        for title, details in EHDI_AT_LEAST_SECTIONS.items()
        if title not in present_titles and details["loinc"] not in present_codes
    ]
    missing_optional = [
        title
        for title, details in OPTIONAL_PATIENT_SUMMARY_SECTIONS.items()
        if title not in present_titles and details["loinc"] not in present_codes
    ]

    return {
        "source": path.name,
        "resource_counts": Counter(resource.get("resourceType") for resource in resources),
        "composition_found": composition is not None,
        "composition_title": composition.get("title") if composition else None,
        "composition_status": composition.get("status") if composition else None,
        "section_titles": [section_title(section) for section in sections],
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "missing_references": uuid_reference_gaps(bundle),
    }


def align_bundle(bundle: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    aligned = copy.deepcopy(bundle)
    composition = find_composition(aligned)
    changes: list[str] = []

    if not composition:
        changes.append("No Composition resource found; no structural section changes made.")
        return aligned, changes

    sections = composition.setdefault("section", [])
    present_codes = {section_code(section) for section in sections}
    present_titles = {section_title(section) for section in sections}

    for title, details in EHDI_AT_LEAST_SECTIONS.items():
        if title in present_titles or details["loinc"] in present_codes:
            continue
        sections.append(empty_section(title, details))
        changes.append(
            f"Added explicit empty {title} section for {details['ehdsi_name']} "
            "using list-empty-reason=unavailable."
        )

    if not changes:
        changes.append("No amended section changes were required.")

    return aligned, changes


def report_for(
    results: list[dict[str, Any]],
    changes_by_file: dict[str, list[str]],
    terminology_changes_by_file: dict[str, list[str]],
    terminology_stats_by_file: dict[str, dict[str, int]],
    medication_changes_by_file: dict[str, list[str]],
    medication_stats_by_file: dict[str, dict[str, int]],
    cts_status: str,
    nmpc_status: str,
) -> str:
    lines = [
        "# EHDS Patient Summary Alignment Report",
        "",
        "Generated from the local bundles in `Test_documents/`.",
        "",
        "Alignment baseline used:",
        "",
        "- eHDSI Patient Summary template, effective 2024-04-19.",
        "- At-least-present eHDSI sections: Medication Summary; Allergies and Other Adverse Reactions; List of Surgeries; Active Problems; Medical Devices.",
        "- FHIR Bundle structure and local Composition sections were preserved; missing clinical facts were not invented.",
        f"- CTS terminology enrichment status: {cts_status}.",
        f"- NMPC medication enrichment status: {nmpc_status}.",
        "",
    ]

    for result in results:
        output_name = Path(result["source"]).with_stem(
            Path(result["source"]).stem + "_ehds_aligned"
        ).name
        lines.extend(
            [
                f"## {result['source']}",
                "",
                f"- Aligned output: `EHDS_aligned_FHIR_resouces/{output_name}`",
                f"- Composition found: {result['composition_found']}",
                f"- Composition title/status: {result['composition_title']} / {result['composition_status']}",
                f"- Resource counts: {dict(result['resource_counts'])}",
                f"- Sections present: {', '.join(result['section_titles'])}",
                f"- Missing at-least-present eHDSI sections before alignment: {', '.join(result['missing_required']) or 'None'}",
                f"- Other commonly used Patient Summary sections absent: {', '.join(result['missing_optional']) or 'None'}",
                f"- Missing internal `urn:uuid:` references: {', '.join(result['missing_references']) or 'None'}",
                "",
                "Changes made:",
                "",
            ]
        )
        for change in changes_by_file[result["source"]]:
            lines.append(f"- {change}")
        lines.append("")

        stats = terminology_stats_by_file[result["source"]]
        lines.extend(
            [
                "Terminology enrichment:",
                "",
                f"- CTS lookup attempts: {stats.get('lookups_attempted', 0)}",
                f"- Coding displays added: {stats.get('displays_added', 0)}",
                f"- CTS text search attempts: {stats.get('searches_attempted', 0)}",
                f"- New codings added from exact text matches: {stats.get('codings_added', 0)}",
                f"- Unresolved text-only concepts: {stats.get('unresolved_text_concepts', 0)}",
                "",
            ]
        )
        for change in terminology_changes_by_file[result["source"]]:
            lines.append(f"- {change}")
        lines.append("")

        medication_stats = medication_stats_by_file[result["source"]]
        lines.extend(
            [
                "Medication catalogue enrichment:",
                "",
                f"- MedicationStatements checked: {medication_stats.get('medication_statements_checked', 0)}",
                f"- ATC reverse searches: {medication_stats.get('atc_reverse_searches', 0)}",
                f"- NMPC text searches: {medication_stats.get('text_searches', 0)}",
                f"- NMPC codings added: {medication_stats.get('nmpc_codings_added', 0)}",
                f"- NMPC candidate extensions added: {medication_stats.get('candidate_extensions_added', 0)}",
                f"- External mapping attempts: {medication_stats.get('mapping_attempts', 0)}",
                f"- External mapping codings added: {medication_stats.get('mapping_codings_added', 0)}",
                f"- Ambiguous medication matches: {medication_stats.get('ambiguous_matches', 0)}",
                f"- Unresolved medications: {medication_stats.get('unresolved_medications', 0)}",
                "",
            ]
        )
        for change in medication_changes_by_file[result["source"]]:
            lines.append(f"- {change}")
        lines.append("")

    lines.extend(
        [
            "## Assumptions and Unresolved Items",
            "",
            "- Empty sections use `emptyReason` code `unavailable` because the source bundles did not contain those clinical facts.",
            "- The script does not add clinical devices, immunizations, conditions, observations, or other resource entries unless they already exist in the source bundle.",
            "- CTS-sourced coding changes are conservative: existing codes may receive missing display text from `$lookup`; text-only concepts are coded only when `$expand` returns one exact unambiguous display match.",
            "- NMPC-sourced medication changes are conservative: an asserted NMPC coding is added only for a single unambiguous product match; multiple matches are recorded as candidate extensions for human review.",
            "- GTIN mappings are not asserted by this script because the NMPC testing reference notes GTIN is file-only or sparsely available via API.",
            "- Full conformance still requires validation against the selected EHDS/IPS FHIR profiles and terminology bindings.",
            "- The live HL7 EU build may change over time; record the guide version used before formal sign-off.",
            "",
        ]
    )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Align local Patient Summary FHIR Bundles with EHDS guidance."
    )
    parser.add_argument(
        "--use-cts",
        action="store_true",
        help="Use the Irish HSE Central Terminology Service to complete safe missing coding metadata.",
    )
    parser.add_argument(
        "--cts-env",
        type=Path,
        default=DEFAULT_CTS_ENV_PATH,
        help="Path to a CTS .env file containing CTS_API_BASE_URL, CTS_TOKEN_URL, CTS_CLIENT_ID, and CTS_CLIENT_SECRET.",
    )
    parser.add_argument(
        "--use-nmpc",
        action="store_true",
        help="Use the Irish NMPC API to enrich MedicationStatement coding and product catalogue candidates.",
    )
    parser.add_argument(
        "--nmpc-env",
        type=Path,
        default=DEFAULT_NMPC_ENV_PATH,
        help="Path to an NMPC .env file containing NMPC_API_BASE_URL, NMPC_AUTH_URL, NMPC_CLIENT_ID, and NMPC_CLIENT_SECRET.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.use_cts:
        load_env_file(args.cts_env)
    if args.use_nmpc:
        load_env_file(args.nmpc_env)

    terminology_client = CTSTerminologyClient()
    if not args.use_cts:
        terminology_client.enabled = False
        terminology_client.status = "disabled: run with --use-cts to enable live terminology enrichment"

    nmpc_client = NMPCClient()
    if not args.use_nmpc:
        nmpc_client.enabled = False
        nmpc_client.status = "disabled: run with --use-nmpc to enable live medication catalogue enrichment"

    OUTPUT_DIR.mkdir(exist_ok=True)
    results: list[dict[str, Any]] = []
    changes_by_file: dict[str, list[str]] = {}
    terminology_changes_by_file: dict[str, list[str]] = {}
    terminology_stats_by_file: dict[str, dict[str, int]] = {}
    medication_changes_by_file: dict[str, list[str]] = {}
    medication_stats_by_file: dict[str, dict[str, int]] = {}

    for source_path in sorted(SOURCE_DIR.glob("*.json")):
        bundle = load_bundle(source_path)
        analysis = analyse_bundle(source_path, bundle)
        aligned, changes = align_bundle(bundle)
        terminology_changes, terminology_stats = enrich_terminology(
            aligned, terminology_client
        )
        medication_changes, medication_stats = enrich_medications_with_nmpc(
            aligned, nmpc_client
        )
        output_path = OUTPUT_DIR / f"{source_path.stem}_ehds_aligned.json"

        write_bundle(output_path, aligned)
        results.append(analysis)
        changes_by_file[source_path.name] = changes
        terminology_changes_by_file[source_path.name] = terminology_changes
        terminology_stats_by_file[source_path.name] = terminology_stats
        medication_changes_by_file[source_path.name] = medication_changes
        medication_stats_by_file[source_path.name] = medication_stats

    REPORT_PATH.write_text(
        report_for(
            results,
            changes_by_file,
            terminology_changes_by_file,
            terminology_stats_by_file,
            medication_changes_by_file,
            medication_stats_by_file,
            terminology_client.status,
            nmpc_client.status,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
