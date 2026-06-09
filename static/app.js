const state = {
  preview: null,
  token: localStorage.getItem("quotationhist_token") || "",
};

const fields = ["material_name", "price", "quantity", "unit", "currency", "remark", "record_date", "requester", "supplier", "cas_number"];

function roleHeaders() {
  if (state.token) return { Authorization: `Bearer ${state.token}` };
  return document.querySelector("#adminRole").checked ? { "X-User-Role": "admin" } : {};
}

function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2600);
}

function asJson(form) {
  return Object.fromEntries(new FormData(form).entries());
}

document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.tab}`).classList.add("active");
  });
});

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = asJson(event.currentTarget);
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    toast("登录失败，可继续使用管理员开关进行本地开发");
    return;
  }
  const data = await response.json();
  state.token = data.token;
  localStorage.setItem("quotationhist_token", data.token);
  toast(`已登录：${data.user.email}`);
});

const dropZone = document.querySelector("#dropZone");
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  const input = dropZone.querySelector("input[type=file]");
  input.files = event.dataTransfer.files;
});

document.querySelector("#previewForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const response = await fetch("/api/import/preview", { method: "POST", headers: roleHeaders(), body: formData });
  if (!response.ok) {
    toast(await response.text());
    return;
  }
  state.preview = await response.json();
  renderMapping(state.preview);
  renderPreview(state.preview.preview_rows);
  if (state.preview.is_duplicate) toast("检测到重复文件，仍可确认导入。");
  document.querySelector("#confirmImport").disabled = state.preview.missing_required_fields.length > 0;
});

function renderMapping(preview) {
  const container = document.querySelector("#mappingList");
  container.innerHTML = "";
  preview.headers.forEach((header) => {
    const row = document.createElement("div");
    row.className = "map-row";
    row.innerHTML = `<span>${header}</span><select data-header="${header}"><option value="">忽略</option>${fields
      .map((field) => `<option value="${field}" ${preview.mapping[header] === field ? "selected" : ""}>${field}</option>`)
      .join("")}</select>`;
    container.appendChild(row);
  });
  if (preview.missing_required_fields.length) {
    const warning = document.createElement("p");
    warning.textContent = `缺少必填字段：${preview.missing_required_fields.join(", ")}`;
    warning.style.color = "#b42318";
    container.appendChild(warning);
  }
}

function renderPreview(rows) {
  const container = document.querySelector("#previewRows");
  if (!rows.length) {
    container.textContent = "没有可预览的数据。";
    return;
  }
  container.innerHTML = `<table><thead><tr><th>行</th><th>原始名称</th><th>CAS / 标准名</th><th>价格</th><th>数量</th><th>单位价</th><th>状态</th></tr></thead><tbody>${rows
    .map((row) => {
      const item = row.normalized;
      const material = row.material_candidate;
      return `<tr><td>${row.row_number}</td><td>${item.material_name || ""}</td><td>${material ? `${material.cas_number || "-"} / ${material.standard_name}` : "-"}</td><td>${
        item.price || ""
      }</td><td>${item.quantity_value || ""} ${item.quantity_unit || ""}</td><td>${item.unit_price || ""} / ${item.normalized_unit || ""}</td><td>${row.match_status}</td></tr>`;
    })
    .join("")}</tbody></table>`;
}

document.querySelector("#confirmImport").addEventListener("click", async () => {
  if (!state.preview) return;
  const mapping = {};
  document.querySelectorAll("#mappingList select").forEach((select) => {
    if (select.value) mapping[select.dataset.header] = select.value;
  });
  const payload = {
    filename: state.preview.filename,
    import_type: document.querySelector("#importType").value,
    rows: state.preview.preview_rows,
    mapping,
    uploaded_by: "admin",
    stored_file_id: state.preview.stored_file_id,
  };
  const response = await fetch("/api/import/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...roleHeaders() },
    body: JSON.stringify(payload),
  });
  toast(response.ok ? "导入完成" : await response.text());
  if (response.ok) loadQuotations();
});

async function loadQuotations() {
  const response = await fetch("/api/quotations");
  const data = await response.json();
  const container = document.querySelector("#quotationList");
  if (!data.quotations.length) {
    container.textContent = "暂无报价导入记录。";
    return;
  }
  container.innerHTML = `<table><thead><tr><th>ID</th><th>文件</th><th>客户</th><th>日期</th><th>币种</th><th>行数</th><th>重复</th><th></th></tr></thead><tbody>${data.quotations
    .map(
      (row) =>
        `<tr><td>${row.id}</td><td>${row.filename}</td><td>${row.customer || ""}</td><td>${row.quoted_on || row.imported_at || ""}</td><td>${row.currency}</td><td>${row.line_item_count}</td><td>${
          row.is_duplicate ? "是" : ""
        }</td><td><button class="small danger" data-archive="${row.id}">归档</button></td></tr>`,
    )
    .join("")}</tbody></table>`;
  container.querySelectorAll("[data-archive]").forEach((button) => button.addEventListener("click", () => archiveQuotation(button.dataset.archive)));
}

async function archiveQuotation(id) {
  const response = await fetch(`/api/quotations/${id}`, { method: "DELETE", headers: roleHeaders() });
  toast(response.ok ? "已归档" : await response.text());
  if (response.ok) loadQuotations();
}

async function loadHistory() {
  const catalogNo = document.querySelector("#catalogSearch").value.trim();
  if (!catalogNo) return;
  const response = await fetch(`/api/history/${encodeURIComponent(catalogNo)}`);
  if (!response.ok) {
    toast(await response.text());
    return;
  }
  const data = await response.json();
  const prices = data.history.filter((row) => typeof row.unit_price === "number");
  const max = Math.max(...prices.map((row) => row.unit_price), 1);
  document.querySelector("#historyChart").innerHTML = prices
    .map((row) => `<div class="bar" style="height:${Math.max((row.unit_price / max) * 140, 8)}px" title="${row.quoted_on || row.imported_at}: ${row.unit_price}"></div>`)
    .join("");
  document.querySelector("#historyRows").innerHTML = `<table><thead><tr><th>日期</th><th>客户</th><th>价格</th><th>数量</th><th>文件</th><th>导出</th></tr></thead><tbody>${data.history
    .map(
      (row) =>
        `<tr><td>${row.quoted_on || row.imported_at || ""}</td><td>${row.customer || ""}</td><td>${row.unit_price || ""} ${row.currency || ""}</td><td>${row.quantity || ""} ${
          row.unit || ""
        }</td><td>${row.filename}</td><td><a href="/api/history/${encodeURIComponent(catalogNo)}/export.xlsx">xlsx</a></td></tr>`,
    )
    .join("")}</tbody></table>`;
}

async function loadDashboard() {
  const response = await fetch("/api/analytics/dashboard");
  const data = await response.json();
  document.querySelector("#dashboardContent").innerHTML = `
    <div class="metric"><strong>${data.quotation_count}</strong><span>报价文件</span></div>
    <div><h3>高频产品</h3>${miniTable(data.most_quoted_products, ["catalog_no", "quote_count", "avg_unit_price"])}</div>
    <div><h3>客户统计</h3>${miniTable(data.customer_summary, ["customer", "quotation_count"])}</div>
    <div><h3>最近导入</h3>${miniTable(data.recent_quotations, ["filename", "customer", "line_item_count"])}</div>`;
}

function miniTable(rows, columns) {
  if (!rows.length) return "<p>暂无数据</p>";
  return `<table><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${row[column] || ""}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

document.querySelector("#reloadQuotations").addEventListener("click", loadQuotations);
document.querySelector("#historyButton").addEventListener("click", loadHistory);
document.querySelector("#reloadDashboard").addEventListener("click", loadDashboard);

document.querySelector("#manualForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = asJson(event.currentTarget);
  const response = await fetch("/api/records", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...roleHeaders() },
    body: JSON.stringify(payload),
  });
  toast(response.ok ? "已保存" : await response.text());
  if (response.ok) event.currentTarget.reset();
});

document.querySelector("#searchButton").addEventListener("click", async () => {
  const query = encodeURIComponent(document.querySelector("#searchInput").value);
  const response = await fetch(`/api/materials/search?q=${query}`);
  const data = await response.json();
  const container = document.querySelector("#searchResults");
  container.innerHTML = data.materials
    .map((material) => `<div class="result-item" data-id="${material.id}"><strong>${material.standard_name}</strong><span>${material.cas_number || ""} ${material.chinese_name || ""}</span></div>`)
    .join("");
  container.querySelectorAll(".result-item").forEach((item) => item.addEventListener("click", () => loadMaterialRecords(item.dataset.id)));
});

async function loadMaterialRecords(id) {
  const response = await fetch(`/api/materials/${id}/records`);
  const data = await response.json();
  document.querySelector("#recordDetails").innerHTML = `<h2>${data.material.standard_name}</h2><p class="ok">最新采购单价：${
    data.stats.latest_purchase_unit_price || "-"
  }，最新询价单价：${data.stats.latest_inquiry_unit_price || "-"}</p><table><thead><tr><th>日期</th><th>类型</th><th>价格</th><th>数量</th><th>标准单价</th><th>供应商</th><th>人员</th><th>备注</th></tr></thead><tbody>${data.records
    .map(
      (row) =>
        `<tr><td>${row.record_date || ""}</td><td>${row.record_type}</td><td>${row.price || ""} ${row.currency || ""}</td><td>${row.quantity_value || ""} ${row.quantity_unit || ""}</td><td>${
          row.unit_price || ""
        } / ${row.normalized_unit || ""}</td><td>${row.supplier || ""}</td><td>${row.requester || ""}</td><td>${row.remark || ""}</td></tr>`,
    )
    .join("")}</tbody></table>`;
}

document.querySelector("#quoteForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = asJson(event.currentTarget);
  const response = await fetch("/api/quotations/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  document.querySelector("#quoteResult").innerHTML = `<h2>计算结果</h2><p>物料：${data.material ? data.material.standard_name : "-"}</p><p>成本：${
    data.result.estimated_cost || "-"
  }</p><p>单价来源记录：${data.result.price_source_record_id || "-"}</p><p>${data.result.warning || ""}</p>`;
});
