const setSelected = (buttons, selectedButton) => {
  buttons.forEach((button) => {
    button.setAttribute("aria-selected", String(button === selectedButton));
  });
};

// The exported HTML uses the same script, so all UI state is local DOM toggling.
const showOnly = (selector, activeValue, attribute) => {
  document.querySelectorAll(selector).forEach((panel) => {
    panel.hidden = panel.getAttribute(attribute) !== activeValue;
  });
};

const viewButtons = Array.from(document.querySelectorAll("[data-view-button]"));
viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.dataset.viewButton;
    setSelected(viewButtons, button);
    document.querySelector('[data-view-panel="summary"]').hidden = view !== "summary";
    document.querySelector('[data-view-panel="diff"]').hidden = view !== "diff";
    document.querySelector('[data-view-panel="document"]').hidden = view !== "document";
    document.querySelector("[data-summary-toolbar]").hidden = view !== "summary";
    document.querySelector("[data-diff-toolbar]").hidden = view !== "diff";
    document.querySelector("[data-document-toolbar]").hidden = view !== "document";
  });
});

document.querySelector("[data-variant-select]")?.addEventListener("change", (event) => {
  showOnly("[data-summary-panel]", event.target.value, "data-summary-panel");
});

document.querySelector("[data-diff-select]")?.addEventListener("change", (event) => {
  showOnly("[data-diff-panel]", event.target.value, "data-diff-panel");
});

document.querySelector("[data-patient-select]")?.addEventListener("change", (event) => {
  const url = new URL(window.location.href);
  url.searchParams.set("patient", event.target.value);
  window.location.href = url.toString();
});

document.querySelector("[data-print-document]")?.addEventListener("click", () => {
  window.print();
});
