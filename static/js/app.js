(function () {
  "use strict";
  const banner = document.getElementById("network-status");
  const bannerText = document.getElementById("network-status-text");
  const retryButton = document.getElementById("network-retry");
  let reconnectTimer;

  function showNetworkState(message, type, persistent) {
    if (!banner) return;
    banner.className = `network-status alert alert-${type}`;
    banner.setAttribute("aria-hidden", "false");
    bannerText.textContent = message;
    if (!persistent) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(() => {
        banner.classList.add("d-none");
        banner.setAttribute("aria-hidden", "true");
      }, 4500);
    }
  }

  function setFormBusy(form) {
    if (form.dataset.async === "true" || form.dataset.busy === "true") return;
    form.dataset.busy = "true";
    form.setAttribute("aria-busy", "true");
    const button = form.querySelector("button[type='submit'], input[type='submit']");
    if (!button) return;
    const label = (button.tagName === "INPUT" ? button.value : button.textContent).trim().replace(/…$/, "");
    const lower = label.toLowerCase();
    const busyLabel = lower.includes("save") ? "Saving…" : lower.includes("create") ? "Creating…" : lower.includes("send") ? "Sending…" : lower.includes("update") ? "Updating…" : lower.includes("verify") ? "Verifying…" : "Processing…";
    if (button.tagName === "INPUT") button.value = busyLabel;
    else button.textContent = busyLabel;
    button.disabled = true;
    button.insertAdjacentHTML("afterbegin", '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>');
  }

  document.addEventListener("submit", (event) => setFormBusy(event.target), true);
  window.addEventListener("offline", () => showNetworkState("You are offline. Unsaved changes are kept where possible. Retry when your connection returns.", "warning", true));
  window.addEventListener("online", () => showNetworkState("Connection restored. You can retry your request.", "success", false));
  if (retryButton) retryButton.addEventListener("click", () => window.location.reload());
  if (!navigator.onLine) showNetworkState("You are offline. Some features require an internet connection.", "warning", true);

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const element = event.detail.elt;
    element.setAttribute("aria-busy", "true");
    element.classList.add("is-loading");
  });
  document.body.addEventListener("htmx:afterRequest", (event) => {
    const element = event.detail.elt;
    element.removeAttribute("aria-busy");
    element.classList.remove("is-loading");
    if (!event.detail.successful) showNetworkState("We could not complete that request. Please try again.", "danger", false);
  });
})();
