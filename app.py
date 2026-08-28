"""Flask app for viewing and exporting Patient Summary comparison reports.

The HTTP layer stays intentionally thin. Clinical bundle parsing, summary model
construction, and differential calculations live in ``patient_summary.py`` so
routes only need to select the patient, render HTML, or return JSON.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for  # pyright: ignore[reportMissingImports]

from patient_summary import dashboard_model, smart_bundle_model


app = Flask(__name__)


def _static_text(filename: str) -> str:
    """Read a static asset so it can be embedded into standalone exports."""
    return (Path(app.static_folder) / filename).read_text(encoding="utf-8")


@app.route("/")
def index():
    """Render the interactive browser view for the selected patient bundle."""
    model = dashboard_model(request.args.get("patient"))
    if not model["patient_slug"]:
        return "No patient summary bundles were found in Test_documents.", 404
    return render_template("index.html", **model, export_mode=False)


@app.route("/export/interactive")
def export_interactive_report():
    """Download a standalone HTML report for sharing outside this Flask app."""
    model = dashboard_model(request.args.get("patient"))
    html = render_template(
        "index.html",
        **model,
        export_mode=True,
        export_generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        utility_css=_static_text("export-utilities.css"),
        dashboard_css=_static_text("styles.css"),
        dashboard_js=_static_text("summary.js"),
    )
    filename = f"{model['patient_slug']}-patient-summary-{datetime.now().strftime('%Y%m%d-%H%M')}.html"
    return Response(
        html,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
        mimetype="text/html",
    )


@app.route("/patient/<patient_slug>")
def patient(patient_slug: str):
    """Compatibility route that maps a readable patient URL to the main view."""
    return redirect(url_for("index", patient=patient_slug))


@app.route("/api/summary")
def api_summary():
    """Return the same dashboard model used by the page as JSON."""
    model = dashboard_model(request.args.get("patient"))
    return jsonify(model)


@app.route("/bundle/<patient_slug>/<variant>")
def bundle_view(patient_slug: str, variant: str):
    """Render a smart document view over one FHIR Patient Summary bundle."""
    model = smart_bundle_model(patient_slug, variant)
    return render_template("bundle.html", **model)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5050)
