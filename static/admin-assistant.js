  const inventoryAiLauncher = document.getElementById("inventoryAiLauncher");
  const inventoryAiPanel = document.getElementById("inventoryAiPanel");
  const inventoryAiClose = document.getElementById("inventoryAiClose");
  const inventoryAiForm = document.getElementById("inventoryAiForm");
  const inventoryAiInput = document.getElementById("inventoryAiInput");
  const inventoryAiMessages = document.getElementById("inventoryAiMessages");
  const inventoryAiHistory = [];

  function toggleInventoryAi(open) {
    inventoryAiPanel.hidden = !open;
    inventoryAiLauncher.setAttribute("aria-expanded", String(open));
    if (open) inventoryAiInput.focus();
  }

  function addInventoryAiMessage(text, role) {
    const message = document.createElement("div");
    message.className = "inventory-ai-message " + role;
    message.textContent = text;
    inventoryAiMessages.appendChild(message);
    inventoryAiMessages.scrollTop = inventoryAiMessages.scrollHeight;
    return message;
  }

  function renderInventoryAiAnswer(element, text) {
    const pattern = /(Tổng tồn|Tổng có thể bán|đã giữ|có thể bán|bán được|tồn|giữ|còn|giá(?: đại lý| lẻ| khuyến mãi)?)\s*:?\s+([\d.]+(?:đ)?)/gi;
    element.textContent = "";
    const lines = text.split("\n");
    if (lines.some(line => line.includes("━━"))) {
      element.classList.add("structured");
      lines.forEach((line, lineIndex) => {
        line = line.trim();
        if (!line) return;
        if (line.includes("━━")) {
          const section = document.createElement("div");
          section.className = "inventory-ai-section " + (line.includes("HẾT") ? "out" : "available");
          section.innerHTML = `<span>${line.includes("HẾT") ? "▰" : "⬡"}</span>${line.replace(/━/g, "").trim()}`;
          element.appendChild(section);
          return;
        }
        const item = line.match(/^(\d+)\.\s+(.+?):\s+còn\s+(\d+),\s+giá\s+(.+)$/i);
        if (item) {
          const row = document.createElement("div");
          row.className = "inventory-ai-result-row";
          const name = document.createElement("span");
          name.className = "inventory-ai-result-name";
          name.textContent = `${item[1]}. ${item[2]}`;
          const values = document.createElement("span");
          values.className = "inventory-ai-result-values";
          values.innerHTML = `còn <strong class="inventory-ai-highlight">${item[3]}</strong><span>, giá</span><strong class="inventory-ai-highlight price">${item[4]}</strong>`;
          row.append(name, values);
          element.appendChild(row);
          return;
        }
        const stockItem = line.match(/^(\d+)\.\s+(.+?):\s+tồn\s+(\d+),\s+giữ\s+(\d+),\s+còn\s+(\d+)$/i);
        if (stockItem) {
          const row = document.createElement("div");
          row.className = "inventory-ai-result-row";
          const name = document.createElement("span");
          name.className = "inventory-ai-result-name";
          name.textContent = `${stockItem[1]}. ${stockItem[2]}`;
          const values = document.createElement("span");
          values.className = "inventory-ai-result-values";
          values.innerHTML = `tồn <strong class="inventory-ai-highlight">${stockItem[3]}</strong><span>, giữ</span><strong class="inventory-ai-highlight">${stockItem[4]}</strong><span>, còn</span><strong class="inventory-ai-highlight">${stockItem[5]}</strong>`;
          row.append(name, values);
          element.appendChild(row);
          return;
        }
        const total = line.match(/^Tổng có thể bán:\s*(\d+)$/i);
        if (total) {
          const footer = document.createElement("div");
          footer.className = "inventory-ai-total";
          footer.innerHTML = `<span>▧ &nbsp;Tổng có thể bán</span><strong class="inventory-ai-highlight">${total[1]}</strong>`;
          element.appendChild(footer);
          return;
        }
        const planning = line.match(/^(\d+)\.\s+(.+?):\s+(.+)$/i);
        if (planning) {
          const row = document.createElement("div");
          row.className = "inventory-ai-plan-row";
          const label = document.createElement("span");
          label.textContent = planning[2];
          const value = document.createElement("strong");
          value.className = "inventory-ai-highlight";
          value.textContent = planning[3];
          row.append(label, value);
          element.appendChild(row);
          return;
        }
        const title = document.createElement("div");
        title.className = lineIndex === 0 ? "inventory-ai-answer-title" : "inventory-ai-answer-line";
        title.textContent = line;
        element.appendChild(title);
      });
      return;
    }
    let cursor = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      element.appendChild(document.createTextNode(text.slice(cursor, match.index) + match[1] + " "));
      const highlight = document.createElement("strong");
      highlight.className = "inventory-ai-highlight";
      highlight.textContent = match[2];
      element.appendChild(highlight);
      cursor = pattern.lastIndex;
    }
    element.appendChild(document.createTextNode(text.slice(cursor)));
  }

  async function askInventoryAi(question) {
    const cleanQuestion = question.trim();
    if (!cleanQuestion) return;
    toggleInventoryAi(true);
    addInventoryAiMessage(cleanQuestion, "user");
    inventoryAiHistory.push({ role: "user", content: cleanQuestion });
    inventoryAiInput.value = "";
    inventoryAiInput.disabled = true;
    const loading = addInventoryAiMessage("Đang tra dữ liệu hiện tại…", "assistant loading");
    try {
      const response = await fetch(inventoryAiLauncher.dataset.chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: inventoryAiHistory.slice(-8) })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Không thể xử lý câu hỏi.");
      renderInventoryAiAnswer(loading, data.answer);
      loading.classList.remove("loading");
      inventoryAiHistory.push({ role: "assistant", content: data.answer });
    } catch (error) {
      loading.textContent = error.message || "Không thể kết nối trợ lý.";
      loading.classList.remove("loading");
      loading.classList.add("error");
    } finally {
      inventoryAiInput.disabled = false;
      inventoryAiInput.focus();
    }
  }

  if (inventoryAiLauncher && inventoryAiPanel) {
    inventoryAiLauncher.addEventListener("click", function () { toggleInventoryAi(inventoryAiPanel.hidden); });
    inventoryAiClose.addEventListener("click", function () { toggleInventoryAi(false); });
    inventoryAiForm.addEventListener("submit", function (event) {
      event.preventDefault();
      askInventoryAi(inventoryAiInput.value);
    });
    inventoryAiInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        inventoryAiForm.requestSubmit();
      }
    });
    document.querySelectorAll(".inventory-ai-suggestions button").forEach(function (button) {
      button.addEventListener("click", function () { askInventoryAi(button.dataset.question || ""); });
    });
  }
