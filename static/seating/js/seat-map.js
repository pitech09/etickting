/* Customer reserved-seat selection. The server revalidates every selection at checkout. */
(function () {
  const dataEl = document.getElementById("seat-map-data");
  const categoryDataEl = document.getElementById("ticket-category-data");
  const categoryEl = document.getElementById("seat-ticket-category") || document.querySelector("[name='ticket_category']");
  const quantityEl = document.getElementById("seat-quantity") || document.querySelector("[name='quantity']");
  if (!dataEl || !categoryEl || !quantityEl) return;

  const seatData = JSON.parse(dataEl.textContent);
  const categoryData = categoryDataEl ? JSON.parse(categoryDataEl.textContent) : [];
  const container = document.getElementById("seat-map");
  const selectedList = document.getElementById("selected-seats");
  const totalEl = document.getElementById("selection-total");
  const checkoutBtn = document.getElementById("checkout-btn");
  const seatIdsField = document.querySelector("[name='seat_ids']");
  const checkoutForm = document.querySelector("[data-checkout-form]");
  const selectedSeatIds = new Set();
  (seatIdsField?.value || "").split(",").map((value) => value.trim()).filter(Boolean).forEach((id) => selectedSeatIds.add(id));

  function moneyToMinor(value) {
    if (value === null || value === undefined || String(value).trim() === "") return null;
    const match = String(value).trim().match(/^\d+(?:\.\d{1,2})?$/);
    if (!match) return null;
    const [whole, fraction = ""] = String(value).split(".");
    return (BigInt(whole) * 100n) + BigInt((fraction + "00").slice(0, 2));
  }
  function formatMinor(value) {
    const minor = BigInt(value);
    return `${minor / 100n}.${String(minor % 100n).padStart(2, "0")}`;
  }

  function selectedCategory() {
    const option = categoryEl.options[categoryEl.selectedIndex];
    const data = categoryData.find((category) => String(category.id) === String(categoryEl.value));
    return { ...data, ...option?.dataset };
  }
  function quantity() {
    const max = Number(selectedCategory()?.max || selectedCategory()?.dataMax || seatData.filter((seat) => seat.is_available).length || 1);
    const value = Math.max(1, Math.min(max, Number.parseInt(quantityEl.value, 10) || 1));
    quantityEl.max = String(max);
    quantityEl.value = String(value);
    return value;
  }
  function statusClass(seat) {
    if (seat.status === "blocked") return "seat-blocked";
    if (seat.status === "sold") return "seat-sold";
    if (seat.status === "reserved") return "seat-reserved";
    if (seat.status === "unavailable") return "seat-unavailable";
    return "seat-available";
  }
  function toggleSeat(seat) {
    if (selectedSeatIds.has(seat.id)) selectedSeatIds.delete(seat.id);
    else if (selectedSeatIds.size < quantity()) selectedSeatIds.add(seat.id);
    render();
  }
  function render() {
    container.innerHTML = "";
    const sections = {};
    seatData.forEach((seat) => {
      if (!sections[seat.section]) sections[seat.section] = {};
      if (!sections[seat.section][seat.row]) sections[seat.section][seat.row] = [];
      sections[seat.section][seat.row].push(seat);
    });
    Object.entries(sections).forEach(([sectionName, rows]) => {
      const sectionDiv = document.createElement("div");
      sectionDiv.className = "section-group mb-5";
      const sectionLabel = document.createElement("div");
      sectionLabel.className = "section-label text-center fw-bold mb-2";
      const sectionSeats = Object.values(rows).flat();
      const sectionPrice = sectionSeats.length ? seatPriceMinor(sectionSeats[0]) : null;
      const supplement = sectionSeats.length ? moneyToMinor(sectionSeats[0].section_price_modifier_minor) : null;
      sectionLabel.textContent = `${sectionName} · ${sectionPrice === null ? "Pricing unavailable" : `M ${formatMinor(sectionPrice)} per seat`}${supplement > 0n ? ` (includes M ${formatMinor(supplement)} supplement)` : ""}`;
      sectionDiv.appendChild(sectionLabel);
      Object.entries(rows).forEach(([rowName, seats]) => {
        const rowDiv = document.createElement("div");
        rowDiv.className = "seat-row";
        const rowLabel = document.createElement("div");
        rowLabel.className = "row-label";
        rowLabel.textContent = rowName;
        rowDiv.appendChild(rowLabel);
        seats.forEach((seat) => {
          const isSelected = selectedSeatIds.has(seat.id);
          const button = document.createElement("button");
          button.type = "button";
          button.className = `seat ${statusClass(seat)}${isSelected ? " seat-selected" : ""}`;
          button.textContent = seat.number;
          const price = seatPriceMinor(seat);
          button.title = `${seat.label} · ${price === null ? "Price unavailable" : `M ${formatMinor(price)}`}`;
          button.setAttribute("aria-label", `Seat ${seat.label}, ${isSelected ? "selected" : seat.status}`);
          button.disabled = !seat.is_available && !isSelected;
          if (seat.is_accessible) button.classList.add("seat-accessible");
          if (seat.is_restricted_view) button.classList.add("seat-restricted");
          if (!button.disabled || isSelected) button.addEventListener("click", () => toggleSeat(seat));
          rowDiv.appendChild(button);
        });
        sectionDiv.appendChild(rowDiv);
      });
      container.appendChild(sectionDiv);
    });
    updateSelectionUI();
  }
  function updateSelectionUI() {
    const selected = seatData.filter((seat) => selectedSeatIds.has(seat.id));
    const count = selected.length;
    const prices = selected.map(seatPriceMinor);
    const categoryPrice = moneyToMinor(selectedCategory()?.price_minor ?? selectedCategory()?.price);
    const hasInvalidPrice = categoryPrice === null || prices.some((price) => price === null);
    const total = hasInvalidPrice ? null : prices.reduce((sum, price) => sum + price, 0n);
    selectedList.innerHTML = count ? selected.map((seat, index) => `<span class="badge text-bg-primary me-1 mb-1">${seat.label} · ${prices[index] === null ? "Price unavailable" : `M ${formatMinor(prices[index])}`}</span>`).join("") : '<p class="text-secondary small mb-0">No seats selected yet.</p>';
    totalEl.innerHTML = hasInvalidPrice
      ? '<p class="text-danger small">Pricing is unavailable for one or more selected seats. Please contact the organiser.</p>'
      : `<p class="text-secondary small">${count} of ${quantity()} selected · Total: <span class="fw-bold">M ${total === null ? "—" : formatMinor(total)}</span></p>`;
    if (seatIdsField) seatIdsField.value = Array.from(selectedSeatIds).join(",");
    const validSelection = count === quantity() && !hasInvalidPrice;
    checkoutBtn.disabled = !validSelection;
    checkoutBtn.classList.toggle("disabled", checkoutBtn.disabled);
    const summaryTotal = document.querySelector("[data-checkout-total]");
    const summaryQuantity = document.querySelector("[data-checkout-quantity]");
    const summarySelection = document.querySelector("[data-checkout-selection]");
    if (summarySelection) summarySelection.textContent = selectedCategory()?.name || "Choose a ticket";
    if (summaryQuantity) summaryQuantity.textContent = count ? String(count) : "—";
    if (summaryTotal) summaryTotal.textContent = total === null ? "—" : formatMinor(total);
  }
  function seatPriceMinor(seat) {
    const base = moneyToMinor(seat.section_ticket_price_minor)
      ?? moneyToMinor(selectedCategory()?.price_minor ?? selectedCategory()?.price);
    const supplement = moneyToMinor(seat.section_price_modifier_minor ?? "0.00");
    return base === null || supplement === null ? null : base + supplement;
  }
  quantityEl.addEventListener("input", () => {
    while (selectedSeatIds.size > quantity()) selectedSeatIds.delete(Array.from(selectedSeatIds).pop());
    render();
  });
  categoryEl.addEventListener("change", () => render());
  checkoutBtn.addEventListener("click", (event) => {
    const selected = seatData.filter((seat) => selectedSeatIds.has(seat.id));
    if (selected.length !== quantity() || selected.some((seat) => seatPriceMinor(seat) === null)) return;
    if (checkoutForm) {
      if (seatIdsField) seatIdsField.value = Array.from(selectedSeatIds).join(",");
      return;
    }
    event.preventDefault();
    const params = new URLSearchParams({ ticket_category: categoryEl.value, quantity: String(quantity()), seat_ids: Array.from(selectedSeatIds).join(",") });
    window.location.href = `/orders/${EVENT_ID}/create/?${params.toString()}`;
  });
  render();
})();
