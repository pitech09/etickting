/**
 * Interactive seat map for customer seat selection.
 * Seats are fetched from the server-rendered JSON data.
 * Selected seats are tracked in the browser and sent to checkout.
 */

(function () {
  const dataEl = document.getElementById("seat-map-data");
  if (!dataEl) return;

  const seatData = JSON.parse(dataEl.textContent);
  const container = document.getElementById("seat-map");
  const selectedList = document.getElementById("selected-seats");
  const totalEl = document.getElementById("selection-total");
  const checkoutBtn = document.getElementById("checkout-btn");

  const selectedSeatIds = new Set();
  const SELECTION_PRICE_MINOR = Number(window.SEAT_PRICE_MINOR || 0);

  // Map status to CSS class
  // Uses seat.status from the model (available, blocked, unavailable)
  // Falls back to "unavailable" for any unknown status
  function statusClass(status) {
    if (status === "blocked") return "seat-blocked";
    if (status === "unavailable") return "seat-unavailable";
    return "seat-available";
  }

  function render() {
    container.innerHTML = "";

    // Group seats by section for visual layout
    const sections = {};
    seatData.forEach((s) => {
      if (!sections[s.section]) sections[s.section] = [];
      sections[s.section].push(s);
    });

    Object.keys(sections).forEach((sectionName) => {
      const sectionDiv = document.createElement("div");
      sectionDiv.className = "section-group mb-5";

      const sectionLabel = document.createElement("div");
      sectionLabel.className = "section-label text-center fw-bold mb-2";
      sectionLabel.textContent = sectionName;
      sectionDiv.appendChild(sectionLabel);

      // Group by row within section
      const rows = {};
      sections[sectionName].forEach((s) => {
        if (!rows[s.row]) rows[s.row] = [];
        rows[s.row].push(s);
      });

      Object.keys(rows).forEach((rowName) => {
        const rowDiv = document.createElement("div");
        rowDiv.className = "seat-row d-flex justify-content-center align-items-center gap-1 mb-3";

        const rowLabel = document.createElement("div");
        rowLabel.className = "row-label text-end me-2 small fw-semibold";
        rowLabel.style.minWidth = "24px";
        rowLabel.textContent = rowName;
        rowDiv.appendChild(rowLabel);

        rows[rowName].forEach((seat) => {
          const seatBtn = document.createElement("button");
          seatBtn.type = "button";
          seatBtn.className = `seat ${statusClass(seat.status)} ${selectedSeatIds.has(seat.id) ? "seat-selected" : ""}`;
          seatBtn.dataset.seatId = seat.id;
          seatBtn.dataset.label = seat.label;
          seatBtn.dataset.status = seat.status;
          seatBtn.dataset.section = seat.section;
          seatBtn.dataset.row = seat.row;
          seatBtn.dataset.number = seat.number;
          seatBtn.setAttribute("aria-label", `Seat ${seat.label}, ${seat.status}`);
          seatBtn.title = seat.label;

          if (seat.is_accessible) seatBtn.classList.add("seat-accessible");
          if (seat.is_restricted_view) seatBtn.classList.add("seat-restricted");

          if (seat.is_available && !selectedSeatIds.has(seat.id)) {
            seatBtn.addEventListener("click", () => toggleSeat(seat.id, seat.label));
          }

          rowDiv.appendChild(seatBtn);
        });

        sectionDiv.appendChild(rowDiv);
      });

      container.appendChild(sectionDiv);
    });

    updateSelectionUI();
  }

  function toggleSeat(seatId, seatLabel) {
    if (!selectedSeatIds.has(seatId) && selectedSeatIds.size >= 1) {
      selectedSeatIds.clear();
    }
    if (selectedSeatIds.has(seatId)) {
      selectedSeatIds.delete(seatId);
    } else {
      selectedSeatIds.add(seatId);
    }
    render();
  }

  function updateSelectionUI() {
    const count = selectedSeatIds.size;
    const totalMinor = count * SELECTION_PRICE_MINOR;
    const totalMajor = (totalMinor / 100).toFixed(2);

    if (count === 0) {
      selectedList.innerHTML = '<p class="text-secondary small mb-0">No seats selected yet.</p>';
      totalEl.innerHTML = '<p class="text-secondary small">Total: <span class="fw-bold">M0.00</span></p>';
      checkoutBtn.disabled = true;
      checkoutBtn.classList.add("disabled");
    } else {
      const labels = Array.from(document.querySelectorAll(".seat-selected")).map(
        (btn) => btn.dataset.label
      );
      selectedList.innerHTML = labels.map((l) => `<span class="badge text-bg-primary me-1 mb-1">${l}</span>`).join("");
      totalEl.innerHTML = `<p class="text-secondary small">Total: <span class="fw-bold">M${totalMajor}</span></p>`;
      checkoutBtn.disabled = false;
      checkoutBtn.classList.remove("disabled");
    }
  }

  // Initialize
  render();

  // Checkout button: store selection in session and redirect
  checkoutBtn.addEventListener("click", () => {
    if (selectedSeatIds.size === 0) return;
    // Store selected seats in sessionStorage for checkout flow
    sessionStorage.setItem("selected_seats", JSON.stringify(Array.from(selectedSeatIds)));
    // Navigate to ticket category selection / checkout
    // The actual URL will be wired up in Phase 4 (Orders)
    window.location.href = `/orders/${EVENT_ID}/create/?seat=${encodeURIComponent(Array.from(selectedSeatIds)[0])}`;
  });
})();
