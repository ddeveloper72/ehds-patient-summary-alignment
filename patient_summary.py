"""Patient Summary loading, rendering model, and bundle differential helpers.

The viewer compares three representations of the same source patient summary:

* ``ips``: the original local IPS source bundle from ``Test_documents``.
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
GAZELLE_DIR = ALIGNED_DIR / "gazelle"

SUMMARY_VARIANTS = {
    "ips": {
        "label": "IPS",
        "description": "Original International Patient Summary source bundle.",
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
    """Return the first coded section code, usually the LOINC code."""
    for coding in section.get("code", {}).get("coding", []):
        if coding.get("code"):
            return str(coding["code"])
    return ""


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


def patient_identifier(patient: dict[str, Any] | None) -> str:
    """Return the first available Patient.identifier value or a safe fallback."""
    if not patient:
        return "Not recorded"
    for identifier in patient.get("identifier", []):
        if identifier.get("value"):
            return str(identifier["value"])
    return patient.get("id") or "Not recorded"


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
        display_from_codeable(resource.get("medicationCodeableConcept")),
        display_from_codeable(resource.get("vaccineCode")),
        display_from_codeable(resource.get("type")),
        resource.get("status"),
        resource.get("id"),
    ]
    detail = next((str(item) for item in candidates if item), "")
    return f"{resource_type}: {detail}" if detail else str(resource_type)


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

    for section in composition.get("section", []):
        entries = summarize_section_entries(section, index)
        sections.append(
            {
                "key": section_key(section),
                "title": section.get("title") or section_code(section) or "Untitled section",
                "code": section_code(section) or "No code",
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
        "summary": {
            "resource_count": len(resources),
            "section_count": len(sections),
            "clinical_entry_count": sum(section["entry_count"] for section in sections),
            "resource_counts": dict(sorted(counts.items())),
        },
        "sections": sections,
        "raw": bundle,
    }


def patient_slug(path: Path) -> str:
    """Convert a source bundle filename into a URL-friendly patient slug."""
    return path.stem.removesuffix("_bundle").replace("_", "-").casefold()


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
    if variant == "ips":
        return source_path
    if variant == "irish":
        candidate = ALIGNED_DIR / f"{source_path.stem}_ehds_aligned.json"
        return candidate if candidate.exists() else None
    if variant == "ehds":
        eps_candidate = GAZELLE_DIR / f"{source_path.stem}_eps_gazelle.json"
        ips_candidate = GAZELLE_DIR / f"{source_path.stem}_ips_gazelle.json"
        aligned_candidate = ALIGNED_DIR / f"{source_path.stem}_ehds_aligned.json"
        for candidate in (eps_candidate, ips_candidate, aligned_candidate):
            if candidate.exists():
                return candidate
    return None


def available_patients() -> list[dict[str, str]]:
    """List all source bundles that can be selected in the UI."""
    patients = []
    for path in sorted(SOURCE_DIR.glob("*_bundle.json")):
        patients.append({"slug": patient_slug(path), "label": patient_label(path)})
    return patients


def source_path_for(slug: str) -> Path:
    """Resolve a patient slug to a source IPS bundle, falling back to the first."""
    fallback: Path | None = None
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
