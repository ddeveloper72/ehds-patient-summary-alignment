"""Patient Summary loading, rendering model, and bundle differential helpers.

The viewer compares three representations of the same source patient summary:

* ``ips``: the validator-facing IPS copy when present, otherwise the local
  source bundle from ``Test_documents``.
* ``ehds``: the validator-facing EHDS/EU bundle when present, falling back to
  the aligned bundle if no Gazelle copy exists.
* ``irish``: the internally useful EHDS-aligned Irish enhanced bundle.

This module does not change clinical content. It adapts FHIR Bundle JSON into a
template-friendly model and calculates lightweight section/resource
differentials for reviewers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "Test_documents"
ALIGNED_DIR = ROOT / "EHDS_aligned_FHIR_resouces"
PATIENTS_DIR = ALIGNED_DIR / "patients"

SUMMARY_VARIANTS = {
    "ips": {
        "label": "IPS",
        "description": "IPS validator-facing patient summary bundle where available.",
    },
    "ehds": {
        "label": "EHDS",
        "description": "EHDS/EU validator-facing patient summary bundle where available.",
    },
    "irish": {
        "label": "Irish Fully Enhanced",
        "description": "EHDS-aligned Irish enhanced bundle with local terminology enrichment.",
    },
}

DIFF_MODES = {
    "ips-ehds": ("ips", "ehds", "IPS vs EHDS"),
    "ips-irish": ("ips", "irish", "IPS vs Irish Fully Enhanced"),
    "ehds-irish": ("ehds", "irish", "EHDS vs Irish Fully Enhanced"),
}


def load_bundle(path: Path) -> dict[str, Any]:
    """Load one FHIR Bundle JSON document from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def bundle_resources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return resource objects from Bundle.entry values, ignoring malformed rows."""
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
    ]


def find_resource(bundle: dict[str, Any], resource_type: str) -> dict[str, Any] | None:
    """Return the first resource of a given FHIR resourceType from a bundle."""
    return next(
        (
            resource
            for resource in bundle_resources(bundle)
            if resource.get("resourceType") == resource_type
        ),
        None,
    )


def find_composition(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Return the document Composition that drives the patient summary sections."""
    return find_resource(bundle, "Composition")


def section_code(section: dict[str, Any]) -> str:
    """Return the first available section code, regardless of coding system."""
    for coding in section.get("code", {}).get("coding", []):
        if coding.get("code"):
            return str(coding["code"])
    return ""


def codeable_codings(value: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return display-ready codings directly from a FHIR CodeableConcept."""
    if not isinstance(value, dict):
        return []
    return [
        {
            "system": str(coding.get("system") or "Unspecified code system"),
            "code": str(coding.get("code") or "No code"),
            "display": str(coding.get("display") or ""),
        }
        for coding in value.get("coding", [])
        if isinstance(coding, dict) and (coding.get("system") or coding.get("code"))
    ]


def section_key(section: dict[str, Any]) -> str:
    """Build a stable comparison key from the section code and title."""
    code = section_code(section)
    title = str(section.get("title") or code or "Untitled section")
    return f"{code}|{title.casefold()}"


def display_from_codeable(value: dict[str, Any] | None) -> str:
    """Extract a human-readable value from a FHIR CodeableConcept-like object."""
    if not isinstance(value, dict):
        return ""
    if value.get("text"):
        return str(value["text"])
    for coding in value.get("coding", []):
        if coding.get("display"):
            return str(coding["display"])
        if coding.get("code"):
            return str(coding["code"])
    return ""


def human_name(patient: dict[str, Any] | None) -> str:
    """Return the best display name from a FHIR Patient resource."""
    if not patient:
        return "Unknown patient"
    for name in patient.get("name", []):
        parts = [*name.get("given", []), name.get("family")]
        value = " ".join(str(part) for part in parts if part)
        if value:
            return value
    return patient.get("id") or "Unknown patient"


def human_resource_name(resource: dict[str, Any] | None) -> str:
    """Return a display name for Patient, Practitioner, or Organization resources."""
    if not resource:
        return "Not recorded"
    if resource.get("name") and isinstance(resource["name"], str):
        return str(resource["name"])
    if isinstance(resource.get("name"), list):
        for name in resource["name"]:
            parts = [*name.get("given", []), name.get("family")]
            value = " ".join(str(part) for part in parts if part)
            if value:
                return value
    return resource.get("id") or resource.get("resourceType") or "Not recorded"


def patient_identifier(patient: dict[str, Any] | None) -> str:
    """Return the first available Patient.identifier value or a safe fallback."""
    if not patient:
        return "Not recorded"
    for identifier in patient.get("identifier", []):
        if identifier.get("value"):
            return str(identifier["value"])
    return patient.get("id") or "Not recorded"


def format_address(address: dict[str, Any] | None) -> str:
    """Format a FHIR Address into a compact single-line display value."""
    if not isinstance(address, dict):
        return "Not recorded"
    parts = [
        *address.get("line", []),
        address.get("city"),
        address.get("state"),
        address.get("postalCode"),
        address.get("country"),
    ]
    return ", ".join(str(part) for part in parts if part) or "Not recorded"


def format_telecom(items: list[dict[str, Any]] | None) -> str:
    """Format FHIR ContactPoint values such as phone and email."""
    if not isinstance(items, list):
        return "Not recorded"
    values = []
    for item in items:
        system = item.get("system")
        value = item.get("value")
        use = item.get("use")
        if value:
            prefix = f"{system}: " if system else ""
            suffix = f" ({use})" if use else ""
            values.append(f"{prefix}{value}{suffix}")
    return "; ".join(values) if values else "Not recorded"


def codeable_list(values: list[dict[str, Any]] | None) -> str:
    """Format a list of CodeableConcept values as display text."""
    if not isinstance(values, list):
        return "Not recorded"
    labels = [display_from_codeable(value) for value in values]
    labels = [label for label in labels if label]
    return ", ".join(labels) if labels else "Not recorded"


def patient_contacts(patient: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return emergency contact, next-of-kin, or guardian details from Patient.contact."""
    if not patient:
        return []
    contacts = []
    for contact in patient.get("contact", []):
        contacts.append(
            {
                "name": human_resource_name({"name": [contact.get("name", {})]}),
                "relationship": codeable_list(contact.get("relationship")),
                "telecom": format_telecom(contact.get("telecom")),
                "address": format_address(contact.get("address")),
            }
        )
    return contacts


def patient_details(
    patient: dict[str, Any] | None, resource_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Build patient demographic, contact, and relationship metadata for display."""
    if not patient:
        return {
            "address": "Not recorded",
            "telecom": "Not recorded",
            "marital_status": "Not recorded",
            "communication": "Not recorded",
            "managing_organization": "Not recorded",
            "general_practitioner": "Not recorded",
            "contacts": [],
        }
    addresses = [format_address(address) for address in patient.get("address", [])]
    languages = []
    for communication in patient.get("communication", []):
        language = display_from_codeable(communication.get("language"))
        if language:
            preferred = " preferred" if communication.get("preferred") else ""
            languages.append(f"{language}{preferred}")
    gps = [
        reference_display(reference, resource_index)
        for reference in patient.get("generalPractitioner", [])
        if isinstance(reference, dict)
    ]
    return {
        "address": "; ".join(addresses) if addresses else "Not recorded",
        "telecom": format_telecom(patient.get("telecom")),
        "marital_status": display_from_codeable(patient.get("maritalStatus")) or "Not recorded",
        "communication": ", ".join(languages) if languages else "Not recorded",
        "managing_organization": reference_display(
            patient.get("managingOrganization"), resource_index
        ),
        "general_practitioner": ", ".join(gps) if gps else "Not recorded",
        "contacts": patient_contacts(patient),
    }


def first_identifier(resource: dict[str, Any] | None) -> str:
    """Return the first identifier value on any FHIR resource."""
    if not resource:
        return "Not recorded"
    identifier = resource.get("identifier")
    if isinstance(identifier, dict):
        return str(identifier.get("value") or identifier.get("system") or "Not recorded")
    if isinstance(identifier, list):
        for item in identifier:
            if item.get("value"):
                return str(item["value"])
    return str(resource.get("id") or "Not recorded")


def resolve_reference(
    reference: dict[str, Any] | None, resource_index: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Resolve a FHIR Reference object against the bundle index."""
    if not isinstance(reference, dict):
        return None
    return resource_index.get(str(reference.get("reference")))


def reference_display(
    reference: dict[str, Any] | None, resource_index: dict[str, dict[str, Any]]
) -> str:
    """Return the display text or resolved resource name for a FHIR reference."""
    if not isinstance(reference, dict):
        return "Not recorded"
    if reference.get("display"):
        return str(reference["display"])
    return human_resource_name(resolve_reference(reference, resource_index))


def clean_xhtml(div: str) -> str:
    """Keep the FHIR narrative HTML browser-friendly without changing content."""
    div = re.sub(r"\s+xmlns=(['\"]).*?\1", "", div)
    div = re.sub(r"<br\s*/?>\s*</br>", "<br>", div)
    return div


def resource_label(resource: dict[str, Any]) -> str:
    """Create a compact display label for a clinical resource."""
    resource_type = resource.get("resourceType", "Resource")
    candidates = [
        display_from_codeable(resource.get("code")),
        display_from_codeable(resource.get("type")),
        display_from_codeable(resource.get("medicationCodeableConcept")),
        display_from_codeable(resource.get("vaccineCode")),
        resource.get("device", {}).get("display") if isinstance(resource.get("device"), dict) else "",
        resource.get("status"),
        resource.get("id"),
    ]
    detail = next((str(item) for item in candidates if item), "")
    return f"{resource_type}: {detail}" if detail else str(resource_type)


def value_from_extension(extension: dict[str, Any]) -> str:
    """Return the primitive value carried by a FHIR extension."""
    for key, value in extension.items():
        if key.startswith("value") and key != "value":
            return str(value)
    return ""


def extension_label(url: str) -> str:
    """Return the compact final segment from an extension URL."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def trace_service(url: str) -> str:
    """Classify local traceability extensions for display."""
    lowered = url.casefold()
    if "nmpc" in lowered:
        return "NMPC API"
    if "cts" in lowered or "datastandards.hse.ie" in lowered:
        return "CTS"
    return "FHIR"


def extension_children(extension: dict[str, Any]) -> dict[str, list[str]]:
    """Group child extension values by their local extension name."""
    grouped: dict[str, list[str]] = {}
    for child in extension.get("extension", []):
        if not isinstance(child, dict):
            continue
        label = extension_label(str(child.get("url", "value")))
        value = value_from_extension(child)
        if value:
            grouped.setdefault(label, []).append(value)
        elif child.get("extension"):
            nested = extension_children(child)
            nested_value = " / ".join(
                ", ".join(values) for values in nested.values() if values
            )
            if nested_value:
                grouped.setdefault(label, []).append(nested_value)
    return grouped


def trace_from_extension(extension: dict[str, Any]) -> dict[str, Any] | None:
    """Build a show-and-tell trace card from a CTS or NMPC extension."""
    url = str(extension.get("url", ""))
    if not any(token in url.casefold() for token in ("cts", "nmpc", "datastandards.hse.ie")):
        return None
    children = extension_children(extension)
    candidates = children.get("candidate", [])
    return {
        "service": trace_service(url),
        "label": extension_label(url),
        "server": ", ".join(children.get("server", [])),
        "operation": ", ".join(children.get("operation", [])),
        "source": " ".join(
            part
            for part in [
                ", ".join(children.get("sourceSystem", [])),
                ", ".join(children.get("sourceCode", [])),
            ]
            if part
        ),
        "total_candidates": ", ".join(children.get("totalCandidates", [])),
        "candidates": candidates[:3],
        "candidate_overflow": max(0, len(candidates) - 3),
    }


def collect_trace_extensions(value: Any) -> list[dict[str, Any]]:
    """Recursively collect local CTS/NMPC traceability extensions."""
    traces = []
    if isinstance(value, dict):
        trace = trace_from_extension(value)
        if trace:
            traces.append(trace)
        for child in value.values():
            traces.extend(collect_trace_extensions(child))
    elif isinstance(value, list):
        for item in value:
            traces.extend(collect_trace_extensions(item))
    return traces


def collect_codings(value: Any, path: str = "resource") -> list[dict[str, str]]:
    """Recursively collect Coding-like objects from a FHIR resource."""
    rows = []
    if isinstance(value, dict):
        if value.get("system") or value.get("code") or value.get("display"):
            traces = collect_trace_extensions(value.get("extension", []))
            rows.append(
                {
                    "path": path,
                    "system": str(value.get("system") or "No system"),
                    "code": str(value.get("code") or "No code"),
                    "display": str(value.get("display") or "No display supplied"),
                    "services": ", ".join(sorted({trace["service"] for trace in traces})),
                }
            )
        for key, child in value.items():
            if key == "extension":
                continue
            rows.extend(collect_codings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value, start=1):
            rows.extend(collect_codings(item, f"{path}[{index}]"))
    return rows


def smart_resource_row(
    reference: str, resource: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Create a display row for a Composition-referenced resource."""
    if not resource:
        return None
    traces = collect_trace_extensions(resource)
    return {
        "reference": reference,
        "type": resource.get("resourceType", "Resource"),
        "id": resource.get("id", "No id"),
        "label": resource_label(resource),
        "codings": collect_codings(resource)[:12],
        "traces": traces[:8],
        "trace_count": len(traces),
        "services": sorted({trace["service"] for trace in traces}),
    }


def reference_index(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index bundle resources by fullUrl and ResourceType/id references."""
    index: dict[str, dict[str, Any]] = {}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if not isinstance(resource, dict):
            continue
        keys = [entry.get("fullUrl")]
        if resource.get("id"):
            keys.append(f"{resource.get('resourceType')}/{resource['id']}")
        for key in keys:
            if key:
                index[str(key)] = resource
    return index


def summarize_section_entries(
    section: dict[str, Any], resource_index: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    """Resolve Composition.section.entry references into display rows."""
    rows = []
    for entry in section.get("entry", []):
        reference = entry.get("reference")
        resource = resource_index.get(reference)
        if resource:
            rows.append(
                {
                    "reference": reference,
                    "label": resource_label(resource),
                    "type": resource.get("resourceType", "Resource"),
                }
            )
    return rows


def bundle_model(path: Path, variant: str) -> dict[str, Any]:
    """Adapt a FHIR Bundle into the structure consumed by the HTML template."""
    bundle = load_bundle(path)
    composition = find_composition(bundle) or {}
    patient = find_resource(bundle, "Patient")
    resources = bundle_resources(bundle)
    index = reference_index(bundle)
    sections = []
    custodian = resolve_reference(composition.get("custodian"), index)
    authors = [
        reference_display(author, index)
        for author in composition.get("author", [])
        if isinstance(author, dict)
    ]

    for section in composition.get("section", []):
        entries = summarize_section_entries(section, index)
        codings = codeable_codings(section.get("code"))
        sections.append(
            {
                "key": section_key(section),
                "title": section.get("title") or section_code(section) or "Untitled section",
                "code": section_code(section) or "No code",
                "codings": codings,
                "empty_reason": display_from_codeable(section.get("emptyReason")),
                "entry_count": len(entries),
                "entries": entries,
                "narrative": clean_xhtml(section.get("text", {}).get("div", "")),
            }
        )

    counts = Counter(resource.get("resourceType", "Unknown") for resource in resources)
    return {
        "variant": variant,
        "variant_label": SUMMARY_VARIANTS[variant]["label"],
        "variant_description": SUMMARY_VARIANTS[variant]["description"],
        "source_file": path.name,
        "bundle_id": bundle.get("id") or "Unknown",
        "bundle_timestamp": bundle.get("timestamp") or composition.get("date") or "Not recorded",
        "composition_title": composition.get("title") or "Patient Summary",
        "composition_status": composition.get("status") or "Not recorded",
        "patient": {
            "name": human_name(patient),
            "identifier": patient_identifier(patient),
            "gender": patient.get("gender", "Not recorded") if patient else "Not recorded",
            "birth_date": patient.get("birthDate", "Not recorded") if patient else "Not recorded",
        },
        "patient_details": patient_details(patient, index),
        "administration": {
            "document_status": composition.get("status") or "Not recorded",
            "document_type": display_from_codeable(composition.get("type")) or "Not recorded",
            "document_date": composition.get("date") or "Not recorded",
            "bundle_timestamp": bundle.get("timestamp") or "Not recorded",
            "bundle_identifier": first_identifier(bundle),
            "bundle_type": bundle.get("type") or "Not recorded",
            "custodian": human_resource_name(custodian),
            "custodian_identifier": first_identifier(custodian),
            "authors": ", ".join(authors) if authors else "Not recorded",
        },
        "summary": {
            "resource_count": len(resources),
            "section_count": len(sections),
            "clinical_entry_count": sum(section["entry_count"] for section in sections),
            "resource_counts": dict(sorted(counts.items())),
        },
        "sections": sections,
        "raw": bundle,
    }


def smart_bundle_model(slug: str, variant: str) -> dict[str, Any]:
    """Build a smart-document view over one selected Patient Summary bundle."""
    source_path = source_path_for(slug)
    if variant not in SUMMARY_VARIANTS:
        variant = "ehds"
    path = variant_path(source_path, variant) or variant_path(source_path, "ehds") or source_path
    variant = next(
        (
            key
            for key in SUMMARY_VARIANTS
            if variant_path(source_path, key) == path
        ),
        variant,
    )
    summary = bundle_model(path, variant)
    bundle = summary["raw"]
    composition = find_composition(bundle) or {}
    index = reference_index(bundle)
    sections = []

    for section in composition.get("section", []):
        section_codings = collect_codings(section.get("code", {}), "Composition.section.code")
        section_code_labels = codeable_codings(section.get("code"))
        rows = []
        for entry in section.get("entry", []):
            reference = str(entry.get("reference") or "")
            row = smart_resource_row(reference, index.get(reference))
            if row:
                rows.append(row)
        section_traces = collect_trace_extensions(section)
        entry_trace_count = sum(row["trace_count"] for row in rows)
        sections.append(
            {
                "title": section.get("title") or section_code(section) or "Untitled section",
                "code": section_code(section) or "No code",
                "code_labels": section_code_labels,
                "narrative": clean_xhtml(section.get("text", {}).get("div", "")),
                "empty_reason": display_from_codeable(section.get("emptyReason")),
                "codings": section_codings,
                "entries": rows,
                "trace_count": len(section_traces) + entry_trace_count,
                "services": sorted(
                    {
                        service
                        for row in rows
                        for service in row["services"]
                    }
                    | {trace["service"] for trace in section_traces}
                ),
            }
        )

    traces = collect_trace_extensions(bundle)
    raw_json = json.dumps(bundle, indent=2, ensure_ascii=False)
    return {
        "patient_slug": patient_slug(source_path),
        "patients": available_patients(),
        "variant": variant,
        "variant_options": [
            {"key": key, **details}
            for key, details in SUMMARY_VARIANTS.items()
            if variant_path(source_path, key)
        ],
        "summary": summary,
        "sections": sections,
        "source_file": path.name,
        "service_counts": dict(Counter(trace["service"] for trace in traces)),
        "trace_count": len(traces),
        "raw_json": raw_json,
    }


def patient_slug(path: Path) -> str:
    """Convert a source bundle filename into a URL-friendly patient slug."""
    patient_dir = patient_dir_for(path)
    if patient_dir:
        return patient_dir.name
    return path.stem.removesuffix("_bundle").replace("_", "-").casefold()


def patient_dir_for(path: Path) -> Path | None:
    """Return the patient workspace folder for a path inside ``patients/``."""
    try:
        relative = path.resolve().relative_to(PATIENTS_DIR.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    return PATIENTS_DIR / relative.parts[0]


def patient_default_bundle_path(patient_dir: Path) -> Path | None:
    """Return the best available bundle path for a patient workspace."""
    for candidate in (
        patient_dir / "source" / "bundle.json",
        patient_dir / "fhir" / "ips-gazelle" / "bundle.json",
        patient_dir / "fhir" / "ehds-aligned" / "bundle.json",
        patient_dir / "fhir" / "eu-eps-gazelle" / "bundle.json",
    ):
        if candidate.exists():
            return candidate
    return None


def patient_label(path: Path) -> str:
    """Return the patient display label used in the patient selector."""
    model = bundle_model(path, "ips")
    return model["patient"]["name"]


def variant_path(source_path: Path, variant: str) -> Path | None:
    """Resolve the bundle file used for a requested comparison variant.

    EHDS prefers the EU/EPS Gazelle-facing bundle because that is the closest
    export to an EHDS validator target. If that file is absent, the IPS Gazelle
    copy and then the internal aligned bundle are acceptable fallbacks for the
    browser comparison.
    """
    patient_dir = patient_dir_for(source_path)

    if variant == "ips":
        if patient_dir:
            ips_candidate = patient_dir / "fhir" / "ips-gazelle" / "bundle.json"
        else:
            ips_candidate = ALIGNED_DIR / "gazelle" / f"{source_path.stem}_ips_gazelle.json"
        return ips_candidate if ips_candidate.exists() else source_path
    if variant == "irish":
        if patient_dir:
            candidate = patient_dir / "fhir" / "ehds-aligned" / "bundle.json"
        else:
            candidate = ALIGNED_DIR / f"{source_path.stem}_ehds_aligned.json"
        return candidate if candidate.exists() else None
    if variant == "ehds":
        if patient_dir:
            eps_candidate = patient_dir / "fhir" / "eu-eps-gazelle" / "bundle.json"
            ips_candidate = patient_dir / "fhir" / "ips-gazelle" / "bundle.json"
            aligned_candidate = patient_dir / "fhir" / "ehds-aligned" / "bundle.json"
        else:
            eps_candidate = ALIGNED_DIR / "gazelle" / f"{source_path.stem}_eps_gazelle.json"
            ips_candidate = ALIGNED_DIR / "gazelle" / f"{source_path.stem}_ips_gazelle.json"
            aligned_candidate = ALIGNED_DIR / f"{source_path.stem}_ehds_aligned.json"
        for candidate in (eps_candidate, ips_candidate, aligned_candidate):
            if candidate.exists():
                return candidate
    return None


def available_patients() -> list[dict[str, str]]:
    """List all source bundles that can be selected in the UI."""
    patients = []
    if PATIENTS_DIR.exists():
        for patient_dir in sorted(path for path in PATIENTS_DIR.iterdir() if path.is_dir()):
            path = patient_default_bundle_path(patient_dir)
            if path:
                patients.append({"slug": patient_dir.name, "label": patient_label(path)})
    if patients:
        return patients
    for path in sorted(SOURCE_DIR.glob("*_bundle.json")):
        patients.append({"slug": patient_slug(path), "label": patient_label(path)})
    return patients


def source_path_for(slug: str) -> Path:
    """Resolve a patient slug to a source IPS bundle, falling back to the first."""
    fallback: Path | None = None
    if PATIENTS_DIR.exists():
        for patient_dir in sorted(path for path in PATIENTS_DIR.iterdir() if path.is_dir()):
            path = patient_default_bundle_path(patient_dir)
            if not path:
                continue
            fallback = fallback or path
            if patient_dir.name == slug:
                return path
        if fallback:
            return fallback
    for path in sorted(SOURCE_DIR.glob("*_bundle.json")):
        fallback = fallback or path
        if patient_slug(path) == slug:
            return path
    if not fallback:
        raise FileNotFoundError("No patient summary bundles were found in Test_documents.")
    return fallback


def load_patient_models(slug: str) -> dict[str, Any]:
    """Load all available variants and selector metadata for one patient."""
    source_path = source_path_for(slug)
    variants = {}
    for variant in SUMMARY_VARIANTS:
        path = variant_path(source_path, variant)
        if path:
            variants[variant] = bundle_model(path, variant)
    return {
        "patient_slug": patient_slug(source_path),
        "patients": available_patients(),
        "variants": variants,
        "variant_options": [
            {"key": key, **details}
            for key, details in SUMMARY_VARIANTS.items()
            if key in variants
        ],
        "diff_options": [
            {"key": key, "left": left, "right": right, "label": label}
            for key, (left, right, label) in DIFF_MODES.items()
            if left in variants and right in variants
        ],
    }


def stable_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Return a resource copy suitable for diff hashing.

    ``meta`` is omitted because it often reflects packaging/profile differences
    rather than a meaningful clinical content change for this reviewer view.
    """
    value = copy.deepcopy(resource)
    value.pop("meta", None)
    return value


def fingerprint(value: Any) -> str:
    """Create a deterministic hash for nested JSON-compatible values."""
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def section_fingerprints(model: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Hash each Composition section at narrative and entry-reference level."""
    return {
        section["key"]: {
            "title": section["title"],
            "code": section["code"],
            "hash": fingerprint(
                {
                    "title": section["title"],
                    "code": section["code"],
                    "empty_reason": section["empty_reason"],
                    "entries": section["entries"],
                    "narrative": re.sub(r"\s+", " ", section["narrative"]).strip(),
                }
            ),
        }
        for section in model["sections"]
    }


def resource_fingerprints(model: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Hash each bundle resource by ResourceType/id for resource-level diffs."""
    rows = {}
    for resource in bundle_resources(model["raw"]):
        key = f"{resource.get('resourceType')}/{resource.get('id', fingerprint(resource)[:10])}"
        rows[key] = {
            "label": resource_label(resource),
            "type": resource.get("resourceType", "Resource"),
            "hash": fingerprint(stable_resource(resource)),
        }
    return rows


def compare_maps(
    left_rows: dict[str, dict[str, str]], right_rows: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Compare keyed hash maps and classify left-only, right-only, and changed."""
    left_keys = set(left_rows)
    right_keys = set(right_rows)
    changed = [
        {
            "key": key,
            "left_label": left_rows[key].get("label") or left_rows[key].get("title"),
            "right_label": right_rows[key].get("label") or right_rows[key].get("title"),
        }
        for key in sorted(left_keys & right_keys)
        if left_rows[key]["hash"] != right_rows[key]["hash"]
    ]
    left_only = [
        {"key": key, "label": left_rows[key].get("label") or left_rows[key].get("title")}
        for key in sorted(left_keys - right_keys)
    ]
    right_only = [
        {"key": key, "label": right_rows[key].get("label") or right_rows[key].get("title")}
        for key in sorted(right_keys - left_keys)
    ]
    return {"left_only": left_only, "right_only": right_only, "changed": changed}


def build_diff(left: dict[str, Any], right: dict[str, Any], label: str) -> dict[str, Any]:
    """Build a section and resource differential between two summary variants."""
    section_diff = compare_maps(section_fingerprints(left), section_fingerprints(right))
    resource_diff = compare_maps(resource_fingerprints(left), resource_fingerprints(right))
    return {
        "label": label,
        "left": left["variant_label"],
        "right": right["variant_label"],
        "sections": section_diff,
        "resources": resource_diff,
        "summary": {
            "sections_added": len(section_diff["right_only"]),
            "sections_removed": len(section_diff["left_only"]),
            "sections_changed": len(section_diff["changed"]),
            "resources_added": len(resource_diff["right_only"]),
            "resources_removed": len(resource_diff["left_only"]),
            "resources_changed": len(resource_diff["changed"]),
        },
    }


def dashboard_model(slug: str | None = None) -> dict[str, Any]:
    """Build the complete page/API model for the selected patient."""
    patients = available_patients()
    selected_slug = slug or (patients[0]["slug"] if patients else "")
    model = load_patient_models(selected_slug)
    diffs = {}
    for option in model["diff_options"]:
        diffs[option["key"]] = build_diff(
            model["variants"][option["left"]],
            model["variants"][option["right"]],
            option["label"],
        )
    model["diffs"] = diffs
    return model
