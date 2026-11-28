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

  const checkoutForm = document.querySelector("[data-checkout-form]");
  const priceDataElement = document.getElementById("ticket-price-data");
  if (checkoutForm && priceDataElement) {
    const category = checkoutForm.querySelector("[name='ticket_category']");
    const quantity = checkoutForm.querySelector("[name='quantity']");
    const selection = document.querySelector("[data-checkout-selection]");
    const quantityOutput = document.querySelector("[data-checkout-quantity]");
    const totalOutput = document.querySelector("[data-checkout-total]");
    const prices = JSON.parse(priceDataElement.textContent);
    function updateCheckoutSummary() {
      const price = Number(prices[category && category.value] || 0);
      const count = Math.max(1, Number(quantity && quantity.value || 1));
      const option = category && category.options[category.selectedIndex];
      if (selection) selection.textContent = option && option.value ? option.textContent : "Choose a ticket";
      if (quantityOutput) quantityOutput.textContent = option && option.value ? String(count) : "—";
      if (totalOutput) totalOutput.textContent = (price * count).toFixed(2);
    }
    if (category) category.addEventListener("change", updateCheckoutSummary);
    if (quantity) quantity.addEventListener("input", updateCheckoutSummary);
    updateCheckoutSummary();
  }

  const countdown = document.querySelector("[data-reservation-countdown]");
  if (countdown) {
    const expiry = Date.parse(countdown.dataset.reservationExpires);
    const output = countdown.querySelector("[data-reservation-countdown-value]");
    const submit = document.querySelector("[data-payment-status]")?.closest("aside")?.querySelector("form button[type='submit']");
    function updateCountdown() {
      const seconds = Math.max(0, Math.floor((expiry - Date.now()) / 1000));
      if (seconds <= 0) {
        output.textContent = "expired";
        countdown.classList.remove("alert-warning");
        countdown.classList.add("alert-danger");
        if (submit) { submit.disabled = true; submit.textContent = "Reservation expired"; }
        return false;
      }
      const minutes = Math.floor(seconds / 60);
      output.textContent = `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
      return true;
    }
    updateCountdown();
    const countdownTimer = window.setInterval(() => { if (!updateCountdown()) window.clearInterval(countdownTimer); }, 1000);
  }

  const paymentPanel = document.querySelector("[data-payment-status]");
  if (paymentPanel) {
    const statusUrl = paymentPanel.dataset.paymentStatusUrl;
    const statusLabel = paymentPanel.querySelector("[data-payment-status-label]");
    const statusMessage = paymentPanel.querySelector("[data-payment-status-message]");
    const refresh = paymentPanel.querySelector("[data-payment-status-refresh]");
    let statusValue = paymentPanel.dataset.paymentStatusValue || "not_submitted";
    let refreshing = false;

    async function refreshPaymentStatus() {
      if (refreshing || !statusUrl || !navigator.onLine) return;
      refreshing = true;
      refresh.disabled = true;
      refresh.textContent = "Checking…";
      try {
        const response = await fetch(statusUrl, { headers: { Accept: "application/json" }, cache: "no-store" });
        if (!response.ok) throw new Error("status request failed");
        const data = await response.json();
        statusValue = data.payment_status || "unknown";
        const labels = { pending: "Pending", initiated: "Initiated", successful: "Successful", failed: "Failed", expired: "Expired", refunded: "Refunded", not_submitted: "Not submitted" };
        statusLabel.textContent = labels[statusValue] || "Unknown";
        statusMessage.textContent = statusValue === "successful" ? "Payment confirmed. Your tickets are available in your wallet." : statusValue === "pending" || statusValue === "initiated" ? "We are waiting for organiser verification. Check again before submitting another payment." : statusValue === "failed" ? "Payment was not confirmed. You can submit a new payment with a different verified reference." : statusValue === "expired" ? "This payment attempt expired. Submit a new payment only if you have not already paid." : statusValue === "unknown" ? "We could not confirm the current status. Your transaction may still be processing; try again shortly." : "Submit payment details to begin verification.";
      } catch (error) {
        statusMessage.textContent = "We could not confirm the current status. Your transaction may still be processing; try again shortly.";
      } finally {
        refreshing = false;
        refresh.disabled = false;
        refresh.textContent = "Refresh status";
      }
    }

    refresh.addEventListener("click", refreshPaymentStatus);
    if (["pending", "initiated"].includes(statusValue)) window.setInterval(refreshPaymentStatus, 15000);
  }

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
