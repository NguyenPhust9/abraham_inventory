  const promotionRows = document.getElementById("promotionRows");
  const promotionBatchForm = document.getElementById("promotionBatchForm");
  const promotionsJson = document.getElementById("promotionsJson");
  const addPromotionRowButton = document.getElementById("addPromotionRow");
  const promotionCodeList = document.getElementById("promotion-code-list");
  const allPromotionCodes = promotionCodeList
    ? Array.from(promotionCodeList.options).map(function (option) { return option.value; })
    : [];

  function validatePromotionCodes(showMessage) {
    const seen = new Map();
    let firstDuplicate = null;
    promotionRows.querySelectorAll(".promotion-code-input").forEach(function (input) {
      const key = input.value.trim().toLocaleLowerCase("vi");
      input.classList.remove("duplicate-code");
      if (!key) return;
      if (seen.has(key)) {
        input.classList.add("duplicate-code");
        seen.get(key).classList.add("duplicate-code");
        if (!firstDuplicate) firstDuplicate = input;
      } else {
        seen.set(key, input);
      }
    });
    if (firstDuplicate && showMessage) {
      firstDuplicate.focus();
      alert("Mã hàng này đã có ở dòng khác. Dữ liệu vẫn được giữ nguyên, vui lòng chọn mã khác.");
    }
    return !firstDuplicate;
  }

  function refreshPromotionCodeOptions() {
    if (!promotionCodeList) return;
    const used = new Set(Array.from(promotionRows.querySelectorAll(".promotion-code-input"))
      .map(function (input) { return input.value.trim().toLocaleLowerCase("vi"); })
      .filter(Boolean));
    promotionCodeList.innerHTML = allPromotionCodes
      .filter(function (code) { return !used.has(code.toLocaleLowerCase("vi")); })
      .map(function (code) { return `<option value="${code.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}">`; })
      .join("");
  }

  function refreshPromotionRowNumbers() {
    promotionRows.querySelectorAll("tr").forEach(function (row, index) {
      row.querySelector(".promotion-row-number").textContent = index + 1;
      row.querySelector(".promotion-remove-row").disabled = promotionRows.children.length === 1;
    });
  }

  function addPromotionRow(promotion) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="promotion-row-number"></td>
      <td><input aria-label="Mã hàng" class="promotion-code-input" list="promotion-code-list" placeholder="Nhập mã hàng" required></td>
      <td><input aria-label="Giá khuyến mãi" class="promotion-price-input" type="text" inputmode="numeric" autocomplete="off" placeholder="1.000.000" required></td>
      <td><select aria-label="Nhãn khuyến mãi" class="promotion-tag-input"><option value="discount">Giảm giá</option><option value="hot">HOT</option></select></td>
      <td><input aria-label="Áp dụng từ" class="promotion-start-input" type="date" required></td>
      <td><input aria-label="Áp dụng tới" class="promotion-end-input" type="date" required></td>
      <td><button type="button" class="promotion-remove-row" title="Xóa dòng"><i data-lucide="trash-2"></i></button></td>`;
    promotionRows.appendChild(row);

    if (promotion) {
      const price = String(promotion.price || "").replace(/\.0+$/, "").replace(/\D/g, "");
      row.querySelector(".promotion-code-input").value = promotion.code || "";
      row.querySelector(".promotion-price-input").dataset.value = price;
      row.querySelector(".promotion-price-input").value = price ? Number(price).toLocaleString("vi-VN") : "";
      row.querySelector(".promotion-tag-input").value = promotion.tag || "discount";
      row.querySelector(".promotion-start-input").value = promotion.start || "";
      row.querySelector(".promotion-end-input").value = promotion.end || "";
    }

    row.querySelector(".promotion-code-input").addEventListener("input", function () {
      validatePromotionCodes(false);
    });
    row.querySelector(".promotion-code-input").addEventListener("change", function () {
      refreshPromotionCodeOptions();
    });
    row.querySelector(".promotion-price-input").addEventListener("input", function () {
      const digits = this.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
      this.dataset.value = digits;
      this.value = digits ? Number(digits).toLocaleString("vi-VN") : "";
    });
    row.querySelector(".promotion-remove-row").addEventListener("click", function () {
      row.remove();
      refreshPromotionRowNumbers();
      validatePromotionCodes(false);
      refreshPromotionCodeOptions();
    });
    refreshPromotionRowNumbers();
    if (window.lucide) window.lucide.createIcons({root: row});
  }

  if (promotionRows && promotionBatchForm && promotionsJson && addPromotionRowButton) {
    addPromotionRowButton.addEventListener("click", function () { addPromotionRow(); });
    document.querySelectorAll(".promotion-edit").forEach(function (button) {
      button.addEventListener("click", function () {
        const existingRow = Array.from(promotionRows.querySelectorAll("tr")).find(function (row) {
          return row.querySelector(".promotion-code-input").value.trim().toLocaleLowerCase("vi") === button.dataset.code.trim().toLocaleLowerCase("vi");
        });
        if (existingRow) {
          existingRow.scrollIntoView({ behavior: "smooth", block: "center" });
          existingRow.querySelector(".promotion-price-input").focus();
          return;
        }
        const blankRow = Array.from(promotionRows.querySelectorAll("tr")).find(function (row) {
          return !row.querySelector(".promotion-code-input").value.trim();
        });
        if (blankRow) blankRow.remove();
        addPromotionRow({
          code: button.dataset.code,
          price: button.dataset.price,
          tag: button.dataset.tag,
          start: button.dataset.start,
          end: button.dataset.end
        });
        validatePromotionCodes(false);
        refreshPromotionCodeOptions();
        promotionBatchForm.scrollIntoView({ behavior: "smooth", block: "start" });
        promotionRows.lastElementChild.querySelector(".promotion-price-input").focus();
      });
    });
    promotionBatchForm.addEventListener("submit", function (event) {
      if (!validatePromotionCodes(true)) {
        event.preventDefault();
        return;
      }
      promotionsJson.value = JSON.stringify(Array.from(promotionRows.querySelectorAll("tr")).map(function (row) {
        const priceInput = row.querySelector(".promotion-price-input");
        return {
          code: row.querySelector(".promotion-code-input").value.trim(),
          promotion_price: priceInput.dataset.value || priceInput.value.replace(/\D/g, ""),
          promotion_tag: row.querySelector(".promotion-tag-input").value,
          promotion_start: row.querySelector(".promotion-start-input").value,
          promotion_end: row.querySelector(".promotion-end-input").value
        };
      }));
    });
    // Carry the batch being edited across list pages, without retaining drafts
    // after a submit or a later visit to the workspace.
    const draftKey = "abraham-promotion-pagination-draft";
    let draft = [];
    try {
      const saved = JSON.parse(sessionStorage.getItem(draftKey) || "null");
      sessionStorage.removeItem(draftKey);
      if (saved && saved.page === location.search && Array.isArray(saved.rows)) draft = saved.rows;
    } catch (_) { /* The form also works when browser storage is unavailable. */ }
    if (draft.length) draft.forEach(addPromotionRow);
    else addPromotionRow();
    refreshPromotionCodeOptions();
    document.querySelectorAll(".pagination a").forEach(function (link) {
      link.addEventListener("click", function (event) {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const rows = Array.from(promotionRows.querySelectorAll("tr")).map(function (row) {
          const price = row.querySelector(".promotion-price-input");
          return {
            code: row.querySelector(".promotion-code-input").value,
            price: price.dataset.value || price.value.replace(/\D/g, ""),
            tag: row.querySelector(".promotion-tag-input").value,
            start: row.querySelector(".promotion-start-input").value,
            end: row.querySelector(".promotion-end-input").value
          };
        }).filter(function (row) { return row.code || row.price || row.start || row.end; });
        try {
          sessionStorage.setItem(draftKey, JSON.stringify({page: new URL(link.href).search, rows: rows}));
        } catch (_) { /* Pagination remains available without session storage. */ }
      });
    });
  }
