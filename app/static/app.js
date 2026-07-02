const state = {
  token: localStorage.getItem("cp_token"),
  user: null,
  templates: [],
  proposals: [],
  currentProposal: null,
  pdfObjectUrl: null,
  introTextEdited: false,
  lastAutoIntroText: "",
  authMode: "login",
};

const $ = (id) => document.getElementById(id);

function toast(message) {
  $("toast").textContent = message;
  $("toast").classList.remove("hidden");
  setTimeout(() => $("toast").classList.add("hidden"), 3200);
}

function money(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

function formatMoney(value) {
  return money(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function addOneMonthIso(value) {
  const date = new Date(value + "T00:00:00");
  const day = date.getDate();
  date.setMonth(date.getMonth() + 1);
  if (date.getDate() !== day) date.setDate(0);
  return date.toISOString().slice(0, 10);
}

function ruDate(value) {
  if (!value) return "";
  const months = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
  ];
  const [year, month, day] = value.split("-");
  return `«${day}» ${months[Number(month) - 1]} ${year} г.`;
}

function numericDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

function buildAutoIntroText() {
  if ($("requestType").value === "with_request" && $("requestNumber").value && $("requestDate").value) {
    return `Изучив направленный Вами запрос №${$("requestNumber").value} от ${numericDate($("requestDate").value)} о предоставлении ценовой информации, мы, нижеподписавшиеся, предлагаем осуществить поставку оборудования, указанного в запросе, подтвержденную прилагаемой таблицей, в которой указана цена единицы товара и общая стоимость:`;
  }
  return "Предлагаем рассмотреть коммерческое предложение на поставку оборудования на следующих условиях.";
}

function buildLegacyAutoIntroTexts() {
  const texts = ["Предлагаем рассмотреть коммерческое предложение на поставку оборудования на следующих условиях."];
  if ($("requestType").value === "with_request" && $("requestNumber").value && $("requestDate").value) {
    texts.push(`Изучив направленный Вами запрос №${$("requestNumber").value} от ${ruDate($("requestDate").value)} о предоставлении ценовой информации, мы предлагаем поставку оборудования на следующих условиях.`);
  }
  return texts;
}

function sameText(left, right) {
  return String(left || "").trim().replace(/\s+/g, " ") === String(right || "").trim().replace(/\s+/g, " ");
}

function isValidInn(value) {
  if (!value) return true;
  if (!/^\d{10}$|^\d{12}$/.test(value)) return false;
  const digits = [...value].map(Number);
  const checksum = (weights, length) => weights.reduce((sum, weight, index) => sum + weight * digits[index], 0) % 11 % 10 === digits[length - 1];
  if (digits.length === 10) return checksum([2, 4, 10, 3, 5, 9, 4, 6, 8], 10);
  return checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 11) && checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 12);
}

function isValidEmail(value) {
  return !value || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value);
}

function keepDigitsOnly(input, maxLength) {
  input.value = input.value.replace(/\D/g, "").slice(0, maxLength);
}

function setRegistryStatus(row, message, kind = "") {
  const status = row.querySelector(".registry-status");
  status.textContent = message;
  status.classList.toggle("ok", kind === "ok");
  status.classList.toggle("error", kind === "error");
}

function scheduleRegistryLookup(row) {
  clearTimeout(row.registryLookupTimer);
  row.registryLookupTimer = setTimeout(() => lookupRegistryProduct(row), 450);
}

async function lookupRegistryProduct(row) {
  const input = row.querySelector(".item-registry-number");
  const number = input.value.trim();
  if (!number) {
    row.dataset.registryNumber = "";
    row.dataset.productName = "";
    setRegistryStatus(row, "");
    return;
  }
  if (row.dataset.registryLookupValue === number) return;
  row.dataset.registryLookupValue = number;
  setRegistryStatus(row, "Ищу...");
  try {
    const product = await api(`/api/registry-products/by-number/${encodeURIComponent(number)}`);
    row.dataset.registryNumber = product.registry_number;
    row.dataset.productName = product.name;
    row.dataset.displayName = product.display_name;
    input.value = product.registry_number;
    row.querySelector(".item-name").value = product.display_name;
    setRegistryStatus(row, "Товар найден", "ok");
  } catch (error) {
    row.dataset.registryNumber = number;
    row.dataset.productName = "";
    setRegistryStatus(row, error.message || "Реестровый номер не найден", "error");
  }
}

function isAutoOrLegacyIntroText(value) {
  const candidates = [state.lastAutoIntroText, buildAutoIntroText(), ...buildLegacyAutoIntroTexts()];
  return String(value || "").trim() === "" || candidates.some((candidate) => sameText(value, candidate));
}

function syncIntroText(force = false) {
  const nextText = buildAutoIntroText();
  const current = $("introText").value;
  if (force || !state.introTextEdited || isAutoOrLegacyIntroText(current)) {
    $("introText").value = nextText;
    state.introTextEdited = false;
  }
  state.lastAutoIntroText = nextText;
}

function outgoingNumber() {
  const value = $("quoteDate").value || todayIso();
  const [year, month, day] = value.split("-");
  return `${day}${month}/${$("outgoingMiddle").value || ""}/М`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = "Ошибка запроса";
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "";
  const encoded = disposition.match(/filename\\*=UTF-8''([^;]+)/i);
  if (encoded) return decodeURIComponent(encoded[1]);
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : "";
}

function basename(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function withAccessToken(url) {
  if (!state.token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}access_token=${encodeURIComponent(state.token)}`;
}

async function apiBlob(path) {
  const response = await fetch(path, { headers: { Authorization: `Bearer ${state.token}` } });
  if (!response.ok) throw new Error("Файл еще не создан");
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
  };
}

function switchView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  $(`view-${name}`).classList.remove("hidden");
  document.querySelectorAll(".nav").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
}

function showAuthed() {
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("userLine").textContent = `${state.user.email} · ${state.user.role === "admin" ? "администратор" : "менеджер"}`;
  $("adminNav").classList.toggle("hidden", state.user.role !== "admin");
}

function showLogin() {
  $("login").classList.remove("hidden");
  $("app").classList.add("hidden");
}

function setAuthMode(mode) {
  state.authMode = mode;
  $("fullNameLabel").classList.toggle("hidden", mode !== "register");
  $("authPassword").minLength = mode === "register" ? 8 : 1;
  $("authSubmit").textContent = mode === "register" ? "Отправить заявку" : "Войти";
  $("loginModeBtn").classList.toggle("active", mode === "login");
  $("registerModeBtn").classList.toggle("active", mode === "register");
  $("loginError").textContent = "";
}

async function bootstrap() {
  if (!state.token) {
    showLogin();
    return;
  }
  try {
    state.user = await api("/api/auth/me");
    showAuthed();
    await Promise.all([loadTemplates(), loadProposals()]);
    if (state.user.role === "admin") await loadAdmin();
    switchView("proposals");
  } catch {
    localStorage.removeItem("cp_token");
    state.token = null;
    showLogin();
    await initAuth();
  }
}

async function loadTemplates() {
  state.templates = await api("/api/templates");
  $("templateId").innerHTML = state.templates.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
}

async function loadProposals() {
  state.proposals = await api("/api/proposals");
  const list = $("proposalList");
  if (!state.proposals.length) {
    list.innerHTML = `<div class="proposal-card"><div><h3>КП пока нет</h3><div class="proposal-meta">Создайте первое коммерческое предложение.</div></div></div>`;
    return;
  }
  list.innerHTML = state.proposals
    .map(
      (p) => `
      <article class="proposal-card">
        <div>
          <h3>${escapeHtml(p.recipient_name)}</h3>
          <div class="proposal-meta">
            <span>${p.outgoing_number || "без номера"}</span>
            <span>${new Date(p.quote_date).toLocaleDateString("ru-RU")}</span>
            <span>${formatMoney(p.total_amount)} ₽</span>
            <span>удаление: ${new Date(p.auto_delete_at).toLocaleDateString("ru-RU")}</span>
            ${p.delete_warning ? `<span class="warning">скоро будет удалено</span>` : ""}
          </div>
        </div>
        <button class="secondary" onclick="editProposal(${p.id})">Открыть</button>
      </article>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
}

function defaultSpecText() {
  return 'Данное коммерческое предложение действительно для конфигурации, описанной в приложении “Спецификация №1”, приложенном к письму.';
}

function resetForm() {
  state.currentProposal = null;
  $("editorMode").textContent = "Новое КП";
  $("proposalForm").reset();
  $("quoteDate").value = todayIso();
  $("validUntil").value = addOneMonthIso(todayIso());
  $("deliveryTermValue").value = "";
  $("warrantyMonths").value = 12;
  $("specificationText").value = defaultSpecText();
  state.introTextEdited = false;
  syncIntroText(true);
  $("itemsBody").innerHTML = "";
  addItem({ unit: "Шт.", quantity: 1, unit_price_vat: 0 });
  $("duplicateBtn").disabled = true;
  $("deleteBtn").disabled = true;
  $("previewBtn").disabled = true;
  $("generateBtn").disabled = true;
  $("docxLink").classList.add("hidden");
  $("pdfLink").classList.add("hidden");
  $("pdfPreview").src = "";
  recalc();
}

function fillForm(p) {
  state.currentProposal = p;
  $("editorMode").textContent = `КП №${p.id}`;
  $("templateId").value = p.template_id;
  $("recipientName").value = p.recipient_name;
  $("recipientInn").value = p.recipient_inn || "";
  $("recipientEmail").value = p.recipient_email || "";
  $("recipientAddress").value = p.recipient_address || "";
  $("recipientUppercase").value = String(Boolean(p.recipient_uppercase));
  $("quoteDate").value = p.quote_date;
  $("outgoingMiddle").value = p.outgoing_number_middle || "";
  $("requestType").value = p.request_type;
  $("requestNumber").value = p.request_number || "";
  $("requestDate").value = p.request_date || "";
  state.lastAutoIntroText = buildAutoIntroText();
  if (!p.intro_text || isAutoOrLegacyIntroText(p.intro_text)) {
    $("introText").value = state.lastAutoIntroText;
    state.introTextEdited = false;
  } else {
    $("introText").value = p.intro_text;
    state.introTextEdited = true;
  }
  $("deliveryTermValue").value = p.delivery_term_value ?? "";
  $("deliveryTermUnit").value = p.delivery_term_unit;
  $("warrantyMonths").value = p.warranty_months;
  $("validUntil").value = p.valid_until;
  $("paymentTerms").value = p.payment_terms || "";
  $("deliveryTerms").value = p.delivery_terms || "";
  $("deliveryPlace").value = p.delivery_place || "";
  $("specificationText").value = p.specification_text ?? defaultSpecText();
  $("itemsBody").innerHTML = "";
  p.items.forEach(addItem);
  $("duplicateBtn").disabled = false;
  $("deleteBtn").disabled = false;
  $("previewBtn").disabled = false;
  $("generateBtn").disabled = false;
  $("docxLink").classList.toggle("hidden", !p.final_docx_path);
  $("pdfLink").classList.toggle("hidden", !p.final_pdf_path);
  $("docxLink").href = p.final_docx_path ? withAccessToken(`/api/proposals/${p.id}/download/docx`) : "#";
  $("pdfLink").href = p.final_pdf_path ? withAccessToken(`/api/proposals/${p.id}/download/pdf`) : "#";
  $("docxLink").download = basename(p.final_docx_path);
  $("pdfLink").download = basename(p.final_pdf_path);
  toggleRequestFields();
  recalc();
}

window.editProposal = async (id) => {
  try {
    const proposal = await api(`/api/proposals/${id}`);
    fillForm(proposal);
    switchView("editor");
  } catch (error) {
    toast(error.message);
  }
};

function addItem(item = {}) {
  const row = document.createElement("tr");
  row.dataset.registryNumber = item.registry_number || "";
  row.dataset.productName = item.product_name || "";
  row.dataset.displayName = item.display_name || item.name || "";
  row.innerHTML = `
    <td class="item-no"></td>
    <td>
      <input class="item-registry-number" value="${escapeHtml(item.registry_number || "")}">
      <span class="registry-status"></span>
    </td>
    <td><textarea class="item-name" required>${escapeHtml(item.display_name || item.name || "")}</textarea></td>
    <td><input class="item-unit" value="${escapeHtml(item.unit || "Шт.")}"></td>
    <td><input class="item-quantity" type="number" min="1" step="1" value="${item.quantity || 1}"></td>
    <td><input class="item-price" type="number" min="0" step="0.01" value="${item.unit_price_vat || 0}"></td>
    <td class="row-total">0,00</td>
    <td><button type="button" class="secondary remove-row">×</button></td>
  `;
  $("itemsBody").append(row);
  row.querySelectorAll("input").forEach((input) => input.addEventListener("input", recalc));
  row.querySelector(".item-name").addEventListener("input", () => {
    row.dataset.displayName = row.querySelector(".item-name").value;
  });
  row.querySelector(".item-registry-number").addEventListener("input", () => {
    row.dataset.registryLookupValue = "";
    scheduleRegistryLookup(row);
  });
  row.querySelector(".remove-row").addEventListener("click", () => {
    row.remove();
    recalc();
  });
  recalc();
}

function collectItems() {
  return [...$("itemsBody").querySelectorAll("tr")].map((row) => {
    const displayName = row.querySelector(".item-name").value;
    return {
    name: displayName,
    registry_number: row.querySelector(".item-registry-number").value.trim() || null,
    product_name: row.dataset.productName || displayName || null,
    display_name: displayName,
    unit: row.querySelector(".item-unit").value || "Шт.",
    quantity: Number(row.querySelector(".item-quantity").value || 1),
    unit_price_vat: Number(row.querySelector(".item-price").value || 0),
  };
  });
}

function collectPayload() {
  syncIntroText(false);
  const deliveryTermValue = $("deliveryTermValue").value.trim();
  const recipientInn = $("recipientInn").value.trim();
  const recipientEmail = $("recipientEmail").value.trim();
  return {
    template_id: Number($("templateId").value),
    recipient_name: $("recipientName").value,
    recipient_inn: recipientInn || null,
    recipient_email: recipientEmail || null,
    recipient_address: $("recipientAddress").value || null,
    recipient_uppercase: $("recipientUppercase").value === "true",
    quote_date: $("quoteDate").value,
    outgoing_number_middle: $("outgoingMiddle").value,
    request_type: $("requestType").value,
    request_number: $("requestNumber").value || null,
    request_date: $("requestDate").value || null,
    delivery_term_value: deliveryTermValue ? Number(deliveryTermValue) : null,
    delivery_term_unit: $("deliveryTermUnit").value,
    warranty_months: Number($("warrantyMonths").value || 0),
    valid_until: $("validUntil").value || null,
    payment_terms: $("paymentTerms").value || null,
    delivery_terms: $("deliveryTerms").value || null,
    delivery_place: $("deliveryPlace").value || null,
    intro_text: $("introText").value || null,
    specification_text: $("specificationText").value,
    items: collectItems(),
  };
}

function recalc() {
  $("outgoingPreview").value = outgoingNumber();
  let total = 0;
  [...$("itemsBody").querySelectorAll("tr")].forEach((row, index) => {
    const qty = Number(row.querySelector(".item-quantity").value || 0);
    const price = Number(row.querySelector(".item-price").value || 0);
    const line = money(qty * price);
    total += line;
    row.querySelector(".item-no").textContent = index + 1;
    row.querySelector(".row-total").textContent = formatMoney(line);
  });
  const vat = money(total * 22 / 122);
  $("totalAmount").textContent = `${formatMoney(total)} ₽`;
  $("vatAmount").textContent = `${formatMoney(vat)} ₽`;
  $("totalWords").textContent = "Сумма прописью формируется сервером при сохранении.";
}

async function saveProposal() {
  const payload = collectPayload();
  if (!payload.recipient_name || !payload.items.length || payload.items.some((i) => !i.display_name)) {
    toast("Заполните адресата и товары");
    return null;
  }
  if (!isValidInn(payload.recipient_inn)) {
    toast("Проверьте ИНН: нужно 10 или 12 цифр с корректной контрольной суммой");
    $("recipientInn").focus();
    return null;
  }
  if (!isValidEmail(payload.recipient_email)) {
    toast("Проверьте email адресата");
    $("recipientEmail").focus();
    return null;
  }
  const path = state.currentProposal ? `/api/proposals/${state.currentProposal.id}` : "/api/proposals";
  const method = state.currentProposal ? "PUT" : "POST";
  const saved = await api(path, { method, body: JSON.stringify(payload) });
  fillForm(saved);
  await loadProposals();
  toast("КП сохранено");
  return saved;
}

function toggleRequestFields() {
  $("requestFields").classList.toggle("hidden", $("requestType").value !== "with_request");
  syncIntroText(false);
}

async function refreshPreview() {
  const saved = await saveProposal();
  if (!saved) return;
  toast("Формирую PDF-предпросмотр");
  const result = await api(`/api/proposals/${saved.id}/preview`, { method: "POST", body: "{}" });
  const { blob } = await apiBlob(result.pdf_url);
  if (state.pdfObjectUrl) URL.revokeObjectURL(state.pdfObjectUrl);
  state.pdfObjectUrl = URL.createObjectURL(blob);
  $("pdfPreview").src = state.pdfObjectUrl;
  toast("Предпросмотр обновлен");
}

async function generateFinal() {
  const saved = await saveProposal();
  if (!saved) return;
  toast("Генерирую DOCX и PDF");
  const result = await api(`/api/proposals/${saved.id}/generate`, { method: "POST", body: "{}" });
  $("docxLink").classList.remove("hidden");
  $("pdfLink").classList.remove("hidden");
  $("docxLink").href = withAccessToken(result.docx_url);
  $("pdfLink").href = withAccessToken(result.pdf_url);
  $("docxLink").download = result.docx_filename || "";
  $("pdfLink").download = result.pdf_filename || "";
  const { blob } = await apiBlob(result.pdf_url);
  if (state.pdfObjectUrl) URL.revokeObjectURL(state.pdfObjectUrl);
  state.pdfObjectUrl = URL.createObjectURL(blob);
  $("pdfPreview").src = state.pdfObjectUrl;
  await loadProposals();
  toast("Файлы готовы");
}

async function loadAdmin() {
  const [users, allowedEmails] = await Promise.all([api("/api/admin/users"), api("/api/admin/allowed-emails")]);
  $("usersList").innerHTML = users
    .map(
      (user) => `
      <div class="admin-row">
        <span>${escapeHtml(user.email)}<br><small>${user.status} · ${user.role}</small></span>
        <span class="inline">
          ${user.status === "pending" ? `<button class="secondary" onclick="approveUser(${user.id})">Одобрить</button>` : ""}
          <button class="secondary" onclick="toggleBlock(${user.id}, '${user.status}')">${user.status === "blocked" ? "Разблокировать" : "Блокировать"}</button>
          <button class="secondary" onclick="toggleRole(${user.id}, '${user.role}')">${user.role === "admin" ? "Сделать менеджером" : "Сделать админом"}</button>
        </span>
      </div>`
    )
    .join("");
  $("allowedEmailsList").innerHTML = allowedEmails.length
    ? allowedEmails
        .map(
          (item) => `
        <div class="admin-row">
          <span>${escapeHtml(item.email)}<br><small>${item.role} · ${item.is_active ? "активен" : "выключен"}</small></span>
        </div>`
        )
        .join("")
    : `<div class="admin-note">Пока нет разрешенных email.</div>`;
  $("templateList").innerHTML = state.templates
    .map((template) => `<div class="admin-row"><span>${escapeHtml(template.name)}<br><small>${escapeHtml(template.organization)}</small></span><strong>v${template.latest_version_id || "—"}</strong></div>`)
    .join("");
}

window.toggleBlock = async (id, status) => {
  await api(`/api/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: status === "blocked" ? "active" : "blocked" }),
  });
  await loadAdmin();
};

window.approveUser = async (id) => {
  await api(`/api/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "active" }),
  });
  await loadAdmin();
};

window.toggleRole = async (id, role) => {
  await api(`/api/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ role: role === "admin" ? "manager" : "admin" }),
  });
  await loadAdmin();
};

document.addEventListener("DOMContentLoaded", () => {
  setAuthMode("login");
  $("loginModeBtn").addEventListener("click", () => setAuthMode("login"));
  $("registerModeBtn").addEventListener("click", () => setAuthMode("register"));
  document.querySelectorAll(".nav").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $("logoutBtn").addEventListener("click", () => {
    localStorage.removeItem("cp_token");
    location.reload();
  });
  $("authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      $("loginError").textContent = "";
      if (state.authMode === "register") {
        await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ email: $("authEmail").value, password: $("authPassword").value, full_name: $("authFullName").value || null }),
        });
        $("authPassword").value = "";
        setAuthMode("login");
        $("loginError").textContent = "Заявка создана. Войти можно после одобрения администратором.";
        return;
      }
      const result = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: $("authEmail").value, password: $("authPassword").value }),
      });
      state.token = result.access_token;
      localStorage.setItem("cp_token", state.token);
      await bootstrap();
    } catch (error) {
      $("loginError").textContent = error.message;
    }
  });
  $("newProposalBtn").addEventListener("click", () => {
    resetForm();
    switchView("editor");
  });
  $("addItemBtn").addEventListener("click", () => addItem());
  $("saveBtn").addEventListener("click", (event) => {
    event.preventDefault();
    saveProposal().catch((error) => toast(error.message));
  });
  $("previewBtn").addEventListener("click", (event) => {
    event.preventDefault();
    refreshPreview().catch((error) => toast(error.message));
  });
  $("generateBtn").addEventListener("click", (event) => {
    event.preventDefault();
    generateFinal().catch((error) => toast(error.message));
  });
  $("duplicateBtn").addEventListener("click", async (event) => {
    event.preventDefault();
    if (!state.currentProposal) return;
    const clone = await api(`/api/proposals/${state.currentProposal.id}/duplicate`, { method: "POST", body: "{}" });
    fillForm(clone);
    await loadProposals();
    toast("КП продублировано");
  });
  $("deleteBtn").addEventListener("click", async (event) => {
    event.preventDefault();
    if (!state.currentProposal || !confirm("Удалить это КП?")) return;
    await api(`/api/proposals/${state.currentProposal.id}`, { method: "DELETE" });
    resetForm();
    await loadProposals();
    switchView("proposals");
    toast("КП удалено");
  });
  $("requestType").addEventListener("change", toggleRequestFields);
  $("recipientInn").addEventListener("input", () => keepDigitsOnly($("recipientInn"), 12));
  ["requestNumber", "requestDate"].forEach((id) => $(id).addEventListener("input", () => syncIntroText(false)));
  $("introText").addEventListener("input", () => {
    state.introTextEdited = !isAutoOrLegacyIntroText($("introText").value);
  });
  ["quoteDate", "outgoingMiddle"].forEach((id) => $(id).addEventListener("input", recalc));
  $("quoteDate").addEventListener("change", () => {
    if (!$("validUntil").value) $("validUntil").value = addOneMonthIso($("quoteDate").value);
  });
  $("templateUploadForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = $("templateFile").files[0];
    if (!file) {
      toast("Выберите DOCX-файл");
      return;
    }
    const data = new FormData();
    data.append("name", $("templateName").value);
    data.append("organization", $("templateOrg").value);
    data.append("file", file);
    await api("/api/admin/templates", { method: "POST", body: data, headers: {} });
    $("templateFile").value = "";
    await loadTemplates();
    await loadAdmin();
    toast("Шаблон загружен");
  });
  $("allowedEmailForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("allowedEmail").value.trim();
    if (!email) {
      toast("Укажите email");
      return;
    }
    await api("/api/admin/allowed-emails", {
      method: "POST",
      body: JSON.stringify({
        email,
        role: $("allowedEmailRole").value,
        is_active: $("allowedEmailActive").checked,
      }),
    });
    $("allowedEmail").value = "";
    $("allowedEmailRole").value = "manager";
    $("allowedEmailActive").checked = true;
    await loadAdmin();
    toast("Email добавлен");
  });
  $("registryUploadForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = $("registryFile").files[0];
    if (!file) {
      toast("Выберите XLSX-файл");
      return;
    }
    const data = new FormData();
    data.append("file", file);
    const result = await api("/api/admin/registry-products/import", { method: "POST", body: data, headers: {} });
    $("registryFile").value = "";
    const errors = result.errors?.length ? `\nОшибки: ${result.errors.join("; ")}` : "";
    $("registryImportResult").textContent = `Создано: ${result.created}\nОбновлено: ${result.updated}\nПропущено: ${result.skipped}${errors}`;
    toast("Реестр товаров загружен");
  });
  resetForm();
  bootstrap();
});
