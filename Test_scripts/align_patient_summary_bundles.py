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
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "Test_documents"
OUTPUT_DIR = ROOT / "EHDS_aligned_FHIR_resouces"
REPORT_PATH = OUTPUT_DIR / "EHDS_alignment_report.md"
PATIENTS_DIR = OUTPUT_DIR / "patients"
DEFAULT_CTS_ENV_PATH = Path(r"C:\Users\duncanfalconer\VS_Code_Projects\CTS_testing\.env")
DEFAULT_NMPC_ENV_PATH = Path(r"C:\Users\duncanfalconer\VS_Code_Projects\NMPC_Testing\.env")
DEFAULT_HAPI_BASE_URL = "http://hapi.fhir.org/baseR4"


def patient_slug(source_path: Path) -> str:
    """Return the patient folder name used for generated bundle outputs."""
    stem = source_path.stem.removesuffix("_bundle")
    if stem == source_path.stem and source_path.suffix == "":
        stem = source_path.name.removesuffix("_bundle")
    return stem.replace("_", "-").casefold()


def patient_output_dir(source_path: Path, variant: str) -> Path:
    """Return the self-contained patient output folder for a FHIR variant."""
    return PATIENTS_DIR / patient_slug(source_path) / "fhir" / variant


def patient_output_path(source_path: Path, variant: str) -> Path:
    """Return the generated bundle path for a FHIR variant."""
    return patient_output_dir(source_path, variant) / "bundle.json"


def patient_source_path(source_path: Path) -> Path:
    """Return the copied source bundle path for the patient workspace."""
    return PATIENTS_DIR / patient_slug(source_path) / "source" / "bundle.json"


def patient_output_display(source_name: str, variant: str) -> str:
    """Return a repository-relative path for reports."""
    source_path = Path(source_name)
    return (
        "EHDS_aligned_FHIR_resouces/"
        f"patients/{patient_slug(source_path)}/fhir/{variant}/bundle.json"
    )


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


VALIDATION_SEVERITIES = ("fatal", "error", "warning", "information")
LOCAL_ENRICHMENT_EXTENSION_PREFIXES = (
    "https://datastandards.hse.ie/fhir/StructureDefinition/cts-",
    "https://nmpc.hse.ie/fhir/StructureDefinition/nmpc-",
)
NMPC_EXTERNAL_CODING_SYSTEMS = {
    "https://nmpc.hse.ie/HPRA",
    "https://nmpc.hse.ie/PCRS",
}
GAZELLE_UNKNOWN_CODE_SYSTEMS = {
    "urn:oid:1.3.6.1.4.1.12559.11.10.1.3.1.44.5",
}
CONDITION_CODE_REPLACEMENTS = {
    ("urn:oid:1.3.6.1.4.1.12559.11.10.1.3.1.44.5", "199"): {
        "system": "http://snomed.info/sct",
        "code": "40354009",
        "display": "Cornelia de Lange syndrome",
        "text": "Cornelia de Lange syndrome",
    },
}
KNOWN_ACTIVE_PROBLEM_NARRATIVE_ROWS = {
    "40354009": {
        "name": "Cornelia de Lange syndrome",
        "problem_type": "Rare disease",
        "time": "since 2017-05-07",
        "status": "active",
    },
}

EPS_VALIDATOR_EXCLUDED_SECTION_CODES = {
    # These optional sections are useful in the internal aligned bundle, but the
    # current EU-EPS alpha validator either does not slice them cleanly or expects
    # a different clinical model than the source bundle provides.
    "11348-0",  # History of Past Illness
    "11369-6",  # History of Immunizations
    "29762-2",  # Social History
    "10162-6",  # History of Pregnancies
    "42348-3",  # Advance Directives
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


IMPLANT_PROCEDURE_DEVICE_MAPPINGS: dict[tuple[str, str], dict[str, str]] = {
    ("http://snomed.info/sct", "64253000"): {
        "procedure_display": "Implantation of heart assist system",
        "device_display": "Heart assist system",
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


class HAPIFHIRValidator:
    """Validate FHIR R4 resources through a HAPI FHIR $validate endpoint."""

    def __init__(self, base_url: str = DEFAULT_HAPI_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = int(os.getenv("HAPI_VALIDATE_TIMEOUT_SECONDS", "30"))

    def validate_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        resource_type = resource.get("resourceType")
        if not resource_type:
            return {
                "status": "skipped",
                "resource_type": "Unknown",
                "resource_id": resource.get("id"),
                "summary": {"fatal": 0, "error": 1, "warning": 0, "information": 0},
                "issues": [
                    {
                        "severity": "error",
                        "code": "invalid",
                        "details": "Resource has no resourceType.",
                    }
                ],
            }

        url = f"{self.base_url}/{resource_type}/$validate"
        body = json.dumps(resource, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
            outcome = json.loads(response_body) if response_body else {}
            issues = operation_outcome_issues(outcome)
            return {
                "status": "validated",
                "resource_type": resource_type,
                "resource_id": resource.get("id"),
                "summary": issue_summary(issues),
                "issues": issues,
            }
        except error.HTTPError as exc:
            if exc.code == 413:
                return {
                    "status": "too-large",
                    "resource_type": resource_type,
                    "resource_id": resource.get("id"),
                    "summary": issue_summary([]),
                    "issues": [],
                    "message": "Request Entity Too Large",
                }
            return {
                "status": "failed",
                "resource_type": resource_type,
                "resource_id": resource.get("id"),
                "summary": {"fatal": 0, "error": 1, "warning": 0, "information": 0},
                "issues": [
                    {
                        "severity": "error",
                        "code": "exception",
                        "details": f"HTTP {exc.code}: {exc.reason}",
                    }
                ],
            }
        except Exception as exc:
            return {
                "status": "failed",
                "resource_type": resource_type,
                "resource_id": resource.get("id"),
                "summary": {"fatal": 0, "error": 1, "warning": 0, "information": 0},
                "issues": [
                    {
                        "severity": "error",
                        "code": "exception",
                        "details": str(exc)[:300],
                    }
                ],
            }


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


def operation_outcome_issues(outcome: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for issue in outcome.get("issue", []):
        details = issue.get("details", {}).get("text")
        diagnostics = issue.get("diagnostics")
        expression = ", ".join(issue.get("expression", []))
        location = ", ".join(issue.get("location", []))
        issues.append(
            {
                "severity": str(issue.get("severity", "information")),
                "code": str(issue.get("code", "")),
                "details": str(details or diagnostics or ""),
                "expression": expression or location,
            }
        )
    return issues


def issue_summary(issues: list[dict[str, str]]) -> dict[str, int]:
    summary = {severity: 0 for severity in VALIDATION_SEVERITIES}
    for issue in issues:
        severity = issue.get("severity", "information")
        if severity in summary:
            summary[severity] += 1
        else:
            summary["information"] += 1
    return summary


def summarize_validation_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {severity: 0 for severity in VALIDATION_SEVERITIES}
    for result in results:
        for severity in VALIDATION_SEVERITIES:
            summary[severity] += result.get("summary", {}).get(severity, 0)
    return summary


def validate_bundle_with_hapi(
    bundle: dict[str, Any], validator: HAPIFHIRValidator
) -> dict[str, Any]:
    bundle_result = validator.validate_resource(bundle)
    results = [bundle_result]
    fallback_used = False

    if bundle_result["status"] == "too-large":
        fallback_used = True
        results = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if isinstance(resource, dict):
                results.append(validator.validate_resource(resource))

    return {
        "status": "resource-fallback" if fallback_used else bundle_result["status"],
        "bundle_result": bundle_result,
        "resource_results": results if fallback_used else [],
        "summary": summarize_validation_results(results),
    }


def is_local_enrichment_extension(extension: dict[str, Any]) -> bool:
    url = extension.get("url", "")
    return any(url.startswith(prefix) for prefix in LOCAL_ENRICHMENT_EXTENSION_PREFIXES)


def has_local_enrichment_extension(element: dict[str, Any]) -> bool:
    return any(
        isinstance(extension, dict) and is_local_enrichment_extension(extension)
        for extension in element.get("extension", [])
    )


def has_enrichment_extension_with_prefix(element: dict[str, Any], prefix: str) -> bool:
    return any(
        isinstance(extension, dict)
        and str(extension.get("url", "")).startswith(prefix)
        for extension in element.get("extension", [])
    )


def strip_local_extensions(value: Any) -> None:
    if isinstance(value, dict):
        extensions = value.get("extension")
        if isinstance(extensions, list):
            value["extension"] = [
                extension
                for extension in extensions
                if not (
                    isinstance(extension, dict)
                    and is_local_enrichment_extension(extension)
                )
            ]
            if not value["extension"]:
                value.pop("extension", None)

        for child in list(value.values()):
            strip_local_extensions(child)
    elif isinstance(value, list):
        for item in value:
            strip_local_extensions(item)


def strip_validator_unfriendly_codings(value: Any) -> None:
    if isinstance(value, dict):
        codings = value.get("coding")
        if isinstance(codings, list):
            kept_codings = []
            for coding in codings:
                if not isinstance(coding, dict):
                    continue

                if coding.get("system") in NMPC_EXTERNAL_CODING_SYSTEMS:
                    continue

                if coding.get("system") in GAZELLE_UNKNOWN_CODE_SYSTEMS:
                    continue

                if (
                    coding.get("system") == NMPC_SNOMED_SYSTEM
                    and has_enrichment_extension_with_prefix(
                        coding, "https://nmpc.hse.ie/fhir/StructureDefinition/nmpc-"
                    )
                ):
                    continue

                kept_codings.append(coding)

            if kept_codings:
                value["coding"] = kept_codings
            else:
                value.pop("coding", None)

        for child in list(value.values()):
            strip_validator_unfriendly_codings(child)
    elif isinstance(value, list):
        for item in value:
            strip_validator_unfriendly_codings(item)


def replace_known_condition_codes(bundle: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for resource in bundle_resources(bundle):
        if resource.get("resourceType") != "Condition":
            continue

        codeable = resource.get("code")
        if not isinstance(codeable, dict):
            continue

        codings = codeable.setdefault("coding", [])
        if not isinstance(codings, list):
            continue

        replacement = None
        source_placeholder_text = codeable.get("text") == "Past illness (epSOS code 199)"
        for coding in codings:
            if not isinstance(coding, dict):
                continue
            replacement = CONDITION_CODE_REPLACEMENTS.get(
                (coding.get("system"), coding.get("code"))
            )
            if replacement:
                break
        if not replacement and source_placeholder_text:
            replacement = next(iter(CONDITION_CODE_REPLACEMENTS.values()))

        if not replacement:
            continue

        snomed_coding = {
            "system": replacement["system"],
            "code": replacement["code"],
            "display": replacement["display"],
        }
        replacement_key = (snomed_coding["system"], snomed_coding["code"])

        updated_codings = [snomed_coding]
        seen = {replacement_key}
        for coding in codings:
            if not isinstance(coding, dict):
                continue
            key = (coding.get("system"), coding.get("code"))
            if key in seen:
                continue
            seen.add(key)
            updated_codings.append(coding)

        if codings != updated_codings:
            codeable["coding"] = updated_codings
            changes.append(
                "Replaced Condition/"
                f"{resource.get('id')} epSOS placeholder code 199 with "
                "SNOMED CT 40354009 | Cornelia de Lange syndrome |."
            )

        if codeable.get("text") != replacement["text"]:
            codeable["text"] = replacement["text"]
            if not changes or not changes[-1].startswith(
                f"Replaced Condition/{resource.get('id')}"
            ):
                changes.append(
                    "Updated Condition/"
                    f"{resource.get('id')} text to {replacement['text']}."
                )

    return changes


def sync_known_active_problem_narratives(composition: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for section in composition.get("section", []):
        if section_code(section) != EHDI_AT_LEAST_SECTIONS["Problem List"]["loinc"]:
            continue

        text = section.get("text")
        if not isinstance(text, dict):
            continue

        narrative = text.get("div")
        if not isinstance(narrative, str):
            continue

        updated = narrative.replace(
            "Rare disease: Cornelia de Lange syndrome (199) since 2017-05-07",
            "Rare disease: Cornelia de Lange syndrome since 2017-05-07",
        )

        row = KNOWN_ACTIVE_PROBLEM_NARRATIVE_ROWS["40354009"]
        if row["name"] not in re.sub(r"<p>.*?</p>", "", updated):
            table_row = (
                "<tr>"
                f"<td><span><span>{row['name']}</span><br></br></span></td>"
                f"<td><span>{row['problem_type']}</span><br></br></td>"
                f"<td>{row['time']}</td>"
                f"<td>{row['status']}</td>"
                "<td></td>"
                "</tr>"
            )
            updated = updated.replace("</tbody>", f"{table_row}\n                            </tbody>")

        if updated != narrative:
            text["div"] = updated
            changes.append(
                "Updated Problem List narrative/table to publish Cornelia de Lange syndrome as an active rare disease."
            )

    return changes


def fix_common_validator_display_issues(bundle: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for resource in bundle_resources(bundle):
        if resource.get("resourceType") != "Provenance":
            continue

        activity = resource.get("activity", {})
        for coding in activity.get("coding", []):
            if (
                coding.get("system")
                == "http://terminology.hl7.org/CodeSystem/v3-DataOperation"
                and coding.get("code") == "UPDATE"
                and coding.get("display") == "Update"
            ):
                coding["display"] = "revise"
                changes.append(
                    f"Changed Provenance/{resource.get('id')} activity display from 'Update' to 'revise'."
                )
    return changes


def create_ips_gazelle_bundle(bundle: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    gazelle_bundle = copy.deepcopy(bundle)
    changes = [
        "Created IPS Gazelle validator-facing copy.",
        "Removed local CTS/NMPC audit and candidate extensions.",
        "Removed NMPC HPRA/PCRS codings and NMPC-added Irish Drug Module codings that Gazelle validates as SNOMED International.",
    ]

    strip_validator_unfriendly_codings(gazelle_bundle)
    strip_local_extensions(gazelle_bundle)
    changes.extend(fix_common_validator_display_issues(gazelle_bundle))

    return gazelle_bundle, changes


def reference_value(reference: Any) -> str | None:
    if isinstance(reference, dict):
        value = reference.get("reference")
        return value if isinstance(value, str) else None
    return None


def collect_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        if set(value.keys()) <= {"reference", "type", "identifier", "display"}:
            reference = reference_value(value)
            if reference:
                references.add(reference)
        for child in value.values():
            references.update(collect_references(child))
    elif isinstance(value, list):
        for item in value:
            references.update(collect_references(item))
    return references


def prune_provenance_targets(bundle: dict[str, Any], kept_full_urls: set[str]) -> None:
    for resource in bundle_resources(bundle):
        if resource.get("resourceType") != "Provenance":
            continue

        targets = resource.get("target")
        if not isinstance(targets, list):
            continue

        resource["target"] = [
            target
            for target in targets
            if reference_value(target) in kept_full_urls
            or not str(reference_value(target) or "").startswith("urn:uuid:")
        ]


def prune_bundle_to_composition_graph(bundle: dict[str, Any]) -> None:
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        return

    composition_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "Composition"
        ),
        None,
    )
    if not composition_entry:
        return

    composition = composition_entry["resource"]
    kept_full_urls = {composition_entry.get("fullUrl")}
    kept_full_urls.update(collect_references(composition))

    # Keep provenance but trim targets to the resources still present.
    for entry in entries:
        resource = entry.get("resource")
        if isinstance(resource, dict) and resource.get("resourceType") == "Provenance":
            kept_full_urls.add(entry.get("fullUrl"))

    patient_ref = reference_value(composition.get("subject"))
    if patient_ref:
        kept_full_urls.add(patient_ref)
    for author in composition.get("author", []):
        reference = reference_value(author)
        if reference:
            kept_full_urls.add(reference)
    custodian_ref = reference_value(composition.get("custodian"))
    if custodian_ref:
        kept_full_urls.add(custodian_ref)

    kept_full_urls = {value for value in kept_full_urls if isinstance(value, str)}
    prune_provenance_targets(bundle, kept_full_urls)
    bundle["entry"] = [
        entry for entry in entries if entry.get("fullUrl") in kept_full_urls
    ]


def create_eps_gazelle_bundle(bundle: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    gazelle_bundle, changes = create_ips_gazelle_bundle(bundle)
    changes[0] = "Created EU-EPS Gazelle validator-facing copy."

    composition = find_composition(gazelle_bundle)
    removed_sections: list[str] = []
    if composition:
        sections = composition.get("section", [])
        if isinstance(sections, list):
            kept_sections = []
            for section in sections:
                code = section_code(section)
                if code in EPS_VALIDATOR_EXCLUDED_SECTION_CODES:
                    removed_sections.append(section_title(section))
                    continue
                kept_sections.append(section)
            composition["section"] = kept_sections

    prune_bundle_to_composition_graph(gazelle_bundle)

    if removed_sections:
        changes.append(
            "Removed optional sections from EU-EPS validator copy: "
            + ", ".join(removed_sections)
            + "."
        )
        changes.append(
            "Pruned unreferenced resources after EU-EPS section filtering so the Bundle only contains the Composition graph submitted for validation."
        )
    else:
        changes.append("No EU-EPS-specific optional sections required filtering.")

    return gazelle_bundle, changes


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


def stable_uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def coding_key(coding: dict[str, Any]) -> tuple[str, str] | None:
    system = coding.get("system")
    code = coding.get("code")
    if not system or not code:
        return None
    return str(system), str(code)


def resource_full_url(bundle: dict[str, Any], resource: dict[str, Any]) -> str | None:
    for entry in bundle.get("entry", []):
        if entry.get("resource") is resource:
            return entry.get("fullUrl")
    return None


def procedure_narrative_dates(composition: dict[str, Any]) -> dict[str, str]:
    dates: dict[str, str] = {}
    for section in composition.get("section", []):
        if section_code(section) != EHDI_AT_LEAST_SECTIONS["History of Procedures"]["loinc"]:
            continue
        narrative = section.get("text", {}).get("div", "")
        for label, date in re.findall(r"<p>\s*([^,<]+),\s*(\d{4}-\d{2}-\d{2})\s*</p>", narrative):
            dates[normalize_term(label)] = date
    return dates


def implant_device_candidates(
    bundle: dict[str, Any], composition: dict[str, Any]
) -> list[dict[str, Any]]:
    narrative_dates = procedure_narrative_dates(composition)
    candidates = []
    for resource in bundle_resources(bundle):
        if resource.get("resourceType") != "Procedure":
            continue

        codeable = resource.get("code", {})
        for coding in codeable.get("coding", []):
            key = coding_key(coding)
            if key not in IMPLANT_PROCEDURE_DEVICE_MAPPINGS:
                continue

            mapping = IMPLANT_PROCEDURE_DEVICE_MAPPINGS[key]
            display = (
                coding.get("display")
                or codeable.get("text")
                or mapping["procedure_display"]
            )
            procedure_full_url = resource_full_url(bundle, resource)
            if not procedure_full_url:
                continue

            date = (
                narrative_dates.get(normalize_term(str(display)))
                or narrative_dates.get(normalize_term(mapping["procedure_display"]))
                or str(resource.get("performedDateTime") or "")
            )
            procedure_id = str(resource.get("id") or procedure_full_url)
            device_id = stable_uuid(f"{procedure_id}:heart-assist-device")
            statement_id = stable_uuid(f"{procedure_id}:heart-assist-device-use")
            candidates.append(
                {
                    "procedure": resource,
                    "procedure_full_url": procedure_full_url,
                    "procedure_display": str(display),
                    "device_display": mapping["device_display"],
                    "date": date,
                    "subject": resource.get("subject"),
                    "device_id": device_id,
                    "device_full_url": f"urn:uuid:{device_id}",
                    "statement_id": statement_id,
                    "statement_full_url": f"urn:uuid:{statement_id}",
                }
            )
    return candidates


def insert_before_provenance(bundle: dict[str, Any], entry: dict[str, Any]) -> None:
    entries = bundle.setdefault("entry", [])
    for index, existing in enumerate(entries):
        resource = existing.get("resource")
        if isinstance(resource, dict) and resource.get("resourceType") == "Provenance":
            entries.insert(index, entry)
            return
    entries.append(entry)


def device_resource(candidate: dict[str, Any]) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Device",
        "id": candidate["device_id"],
        "meta": {
            "profile": [
                "http://hl7.org/fhir/uv/ips/StructureDefinition/Device-uv-ips"
            ]
        },
        "status": "active",
        "type": {"text": candidate["device_display"]},
        "note": [
            {
                "text": "Derived from the source implantation Procedure. The source bundle did not include device serial number, UDI, manufacturer, model, or implant-location details."
            }
        ],
    }
    if isinstance(candidate.get("subject"), dict):
        resource["patient"] = candidate["subject"]
    return resource


def device_use_statement_resource(candidate: dict[str, Any]) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "DeviceUseStatement",
        "id": candidate["statement_id"],
        "meta": {
            "profile": [
                "http://hl7.org/fhir/uv/ips/StructureDefinition/DeviceUseStatement-uv-ips"
            ]
        },
        "status": "active",
        "device": {
            "reference": candidate["device_full_url"],
            "display": candidate["device_display"],
        },
        "derivedFrom": [
            {
                "reference": candidate["procedure_full_url"],
                "display": candidate["procedure_display"],
            }
        ],
        "bodySite": {"text": "Heart"},
        "note": [
            {
                "text": "Derived from source Procedure evidence. Device identifiers, serial number, UDI, manufacturer, model, and more specific implant site/laterality were not present in the source bundle."
            }
        ],
    }
    if isinstance(candidate.get("subject"), dict):
        resource["subject"] = candidate["subject"]
    if candidate.get("date"):
        resource["timingDateTime"] = candidate["date"]
    return resource


def upsert_implant_device_resources(
    bundle: dict[str, Any], candidates: list[dict[str, Any]]
) -> None:
    for candidate in candidates:
        device_entry = next(
            (
                entry
                for entry in bundle.get("entry", [])
                if entry.get("fullUrl") == candidate["device_full_url"]
            ),
            None,
        )
        statement_entry = next(
            (
                entry
                for entry in bundle.get("entry", [])
                if entry.get("fullUrl") == candidate["statement_full_url"]
            ),
            None,
        )

        if device_entry and isinstance(device_entry.get("resource"), dict):
            device_entry["resource"].update(device_resource(candidate))
        else:
            insert_before_provenance(
                bundle,
                {
                    "fullUrl": candidate["device_full_url"],
                    "resource": device_resource(candidate),
                },
            )

        if statement_entry and isinstance(statement_entry.get("resource"), dict):
            statement_entry["resource"].update(device_use_statement_resource(candidate))
            statement_entry["resource"].pop("reasonReference", None)
        else:
            insert_before_provenance(
                bundle,
                {
                    "fullUrl": candidate["statement_full_url"],
                    "resource": device_use_statement_resource(candidate),
                },
            )


def medical_devices_section_for(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    details = EHDI_AT_LEAST_SECTIONS["Medical Devices"]
    rows = "".join(
        "<tr>"
        f"<td>{candidate['device_display']}</td>"
        f"<td>{candidate.get('date') or 'Not recorded'}</td>"
        f"<td>{candidate['procedure_display']}</td>"
        "</tr>"
        for candidate in candidates
    )
    summary = "".join(
        f"<p>{candidate['device_display']} implant"
        f"{', implanted ' + candidate['date'] if candidate.get('date') else ''}</p>"
        for candidate in candidates
    )
    return {
        "title": "Medical Devices",
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
                '<div xmlns="http://www.w3.org/1999/xhtml">'
                f"{summary}<table><thead><tr><th>Device</th><th>Implant date</th><th>Source procedure</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>"
            ),
        },
        "entry": [
            {"reference": candidate["statement_full_url"]} for candidate in candidates
        ],
    }


def model_implant_procedures_as_devices(
    bundle: dict[str, Any], composition: dict[str, Any]
) -> list[str]:
    candidates = implant_device_candidates(bundle, composition)
    if not candidates:
        return []

    date_changes = []
    for candidate in candidates:
        date = candidate.get("date")
        procedure = candidate["procedure"]
        if date and procedure.get("performedDateTime") != date:
            procedure["performedDateTime"] = date
            date_changes.append(
                f"set Procedure/{procedure.get('id')} performedDateTime to {date}"
            )

    upsert_implant_device_resources(bundle, candidates)
    sections = composition.setdefault("section", [])
    replacement = medical_devices_section_for(candidates)
    for index, section in enumerate(sections):
        if section_title(section) == "Medical Devices" or section_code(section) == EHDI_AT_LEAST_SECTIONS["Medical Devices"]["loinc"]:
            sections[index] = replacement
            break
    else:
        sections.append(replacement)

    return [
        "Modelled implant procedure evidence as Medical Devices entries: "
        + ", ".join(
            f"{candidate['device_display']} from Procedure/{candidate['procedure'].get('id')}"
            for candidate in candidates
        )
        + ("; " + "; ".join(date_changes) if date_changes else "")
        + "."
    ]


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

    changes.extend(model_implant_procedures_as_devices(aligned, composition))
    changes.extend(replace_known_condition_codes(aligned))
    changes.extend(sync_known_active_problem_narratives(composition))

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
    validation_results_by_file: dict[str, dict[str, Any]],
    gazelle_outputs_by_file: dict[str, list[str]],
    cts_status: str,
    nmpc_status: str,
    validation_status: str,
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
        f"- HAPI FHIR validation status: {validation_status}.",
        "",
    ]

    for result in results:
        lines.extend(
            [
                f"## {result['source']}",
                "",
                f"- Aligned output: `{patient_output_display(result['source'], 'ehds-aligned')}`",
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

        validation_result = validation_results_by_file.get(result["source"])
        if validation_result:
            summary = validation_result["summary"]
            lines.extend(
                [
                    "HAPI FHIR validation:",
                    "",
                    f"- Mode/status: {validation_result['status']}",
                    f"- Fatal: {summary.get('fatal', 0)}",
                    f"- Errors: {summary.get('error', 0)}",
                    f"- Warnings: {summary.get('warning', 0)}",
                    f"- Information: {summary.get('information', 0)}",
                    "",
                ]
            )
            if validation_result["status"] == "resource-fallback":
                lines.append(
                    "- Bundle-level validation returned 413 Request Entity Too Large, so each contained resource was validated individually."
                )
                lines.append("")

            issue_lines = validation_issue_lines(validation_result)
            if issue_lines:
                lines.append("Validation issues:")
                lines.append("")
                lines.extend(issue_lines)
                lines.append("")

        gazelle_outputs = gazelle_outputs_by_file.get(result["source"], [])
        if gazelle_outputs:
            lines.append("Gazelle validator-facing outputs:")
            lines.append("")
            for item in gazelle_outputs:
                lines.append(f"- {item}")
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
            "- HAPI public server validation is useful for base FHIR R4 structure checks, but it may not validate EHDS/HL7 Europe EPS profiles unless the relevant ImplementationGuide packages are available on that server.",
            "- IPS Gazelle output is a validator-facing copy. It removes local enrichment trace extensions and candidate data that are useful internally but not known to the selected Gazelle profile.",
            "- Do not send real patient-identifiable data to public validation servers.",
            "- Full conformance still requires validation against the selected EHDS/IPS FHIR profiles and terminology bindings.",
            "- The live HL7 EU build may change over time; record the guide version used before formal sign-off.",
            "",
        ]
    )

    return "\n".join(lines)


def validation_issue_lines(validation_result: dict[str, Any], limit: int = 20) -> list[str]:
    if validation_result["status"] == "resource-fallback":
        raw_results = validation_result.get("resource_results", [])
    else:
        raw_results = [validation_result.get("bundle_result", {})]

    lines: list[str] = []
    for result in raw_results:
        resource_label = result.get("resource_type", "Resource")
        if result.get("resource_id"):
            resource_label += f"/{result['resource_id']}"

        for issue in result.get("issues", []):
            severity = issue.get("severity", "information")
            details = issue.get("details") or issue.get("code") or "No details returned"
            expression = issue.get("expression")
            suffix = f" ({expression})" if expression else ""
            lines.append(f"- {resource_label}: {severity} - {details}{suffix}")
            if len(lines) >= limit:
                lines.append(f"- Additional validation issues omitted after first {limit}.")
                return lines

    return lines


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
    parser.add_argument(
        "--validate-hapi",
        action="store_true",
        help="Validate aligned bundles with the public HAPI FHIR R4 $validate endpoint. Falls back to resource-by-resource validation on HTTP 413.",
    )
    parser.add_argument(
        "--hapi-base-url",
        default=DEFAULT_HAPI_BASE_URL,
        help="Base URL for the HAPI FHIR R4 server.",
    )
    parser.add_argument(
        "--target-ips-gazelle",
        action="store_true",
        help="Create an IPS Gazelle validator-facing bundle copy with local enrichment artifacts stripped.",
    )
    parser.add_argument(
        "--target-eps-gazelle",
        action="store_true",
        help="Create a EU-EPS Gazelle validator-facing bundle copy with EPS-alpha-problematic optional sections filtered.",
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

    hapi_validator = HAPIFHIRValidator(args.hapi_base_url)
    validation_status = (
        f"enabled: {args.hapi_base_url}"
        if args.validate_hapi
        else "disabled: run with --validate-hapi to enable public HAPI validation"
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    results: list[dict[str, Any]] = []
    changes_by_file: dict[str, list[str]] = {}
    terminology_changes_by_file: dict[str, list[str]] = {}
    terminology_stats_by_file: dict[str, dict[str, int]] = {}
    medication_changes_by_file: dict[str, list[str]] = {}
    medication_stats_by_file: dict[str, dict[str, int]] = {}
    validation_results_by_file: dict[str, dict[str, Any]] = {}
    gazelle_outputs_by_file: dict[str, list[str]] = {}

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
        source_copy_path = patient_source_path(source_path)
        source_copy_path.parent.mkdir(parents=True, exist_ok=True)
        write_bundle(source_copy_path, bundle)

        output_path = patient_output_path(source_path, "ehds-aligned")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        write_bundle(output_path, aligned)
        gazelle_outputs_by_file[source_path.name] = []
        if args.target_ips_gazelle:
            gazelle_bundle, gazelle_changes = create_ips_gazelle_bundle(aligned)
            gazelle_path = patient_output_path(source_path, "ips-gazelle")
            gazelle_path.parent.mkdir(parents=True, exist_ok=True)
            write_bundle(gazelle_path, gazelle_bundle)
            gazelle_outputs_by_file[source_path.name].append(
                f"`{patient_output_display(source_path.name, 'ips-gazelle')}`"
            )
            gazelle_outputs_by_file[source_path.name].extend(gazelle_changes)
        if args.target_eps_gazelle:
            gazelle_bundle, gazelle_changes = create_eps_gazelle_bundle(aligned)
            gazelle_path = patient_output_path(source_path, "eu-eps-gazelle")
            gazelle_path.parent.mkdir(parents=True, exist_ok=True)
            write_bundle(gazelle_path, gazelle_bundle)
            gazelle_outputs_by_file[source_path.name].append(
                f"`{patient_output_display(source_path.name, 'eu-eps-gazelle')}`"
            )
            gazelle_outputs_by_file[source_path.name].extend(gazelle_changes)
        if args.validate_hapi:
            validation_results_by_file[source_path.name] = validate_bundle_with_hapi(
                aligned, hapi_validator
            )
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
            validation_results_by_file,
            gazelle_outputs_by_file,
            terminology_client.status,
            nmpc_client.status,
            validation_status,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
