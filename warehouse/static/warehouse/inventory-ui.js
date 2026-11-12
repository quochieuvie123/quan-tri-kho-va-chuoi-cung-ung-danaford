(() => {
  const readJSON = (id, fallback) => {
    const node = document.getElementById(id);

    if (!node) {
      return fallback;
    }

    try {
      return JSON.parse(node.textContent);
    } catch {
      return fallback;
    }
  };

  // Mở và đóng các hộp thoại.
  document.querySelectorAll("[data-inv-open]").forEach(button => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.invOpen);

      if (dialog) {
        dialog.showModal();
      }
    });
  });

  document.querySelectorAll("[data-inv-close]").forEach(button => {
    button.addEventListener("click", () => {
      button.closest("dialog").close();
    });
  });

  // Nối bộ chọn kho trên thanh đầu trang.
  const config = readJSON("inventory-warehouses", null);
  const warehouseSelect = document.querySelector(
    ".topbar__branch select"
  );

  if (config && warehouseSelect) {
    warehouseSelect.replaceChildren();

    config.items.forEach(item => {
      warehouseSelect.add(new Option(item.label, item.value));
    });

    warehouseSelect.value = config.selected;
    warehouseSelect.disabled = config.locked;
    warehouseSelect.setAttribute("aria-label", "Kho đang xem");

    warehouseSelect.addEventListener("change", () => {
      const url = new URL(location.href);

      url.searchParams.set("kho", warehouseSelect.value);
      url.searchParams.delete("page");

      location.assign(url);
    });
  }

  // Điền nguyên nhân và phương án theo VIN được chọn.
  const reasonSelect = document.getElementById(
    "inventory-reason-vin"
  );

  if (reasonSelect) {
    const reasons = readJSON("inventory-reason-data", []);

    const updateReason = () => {
      const item = reasons.find(
        item => item.vin === reasonSelect.value
      );

      if (!item) {
        return;
      }

      const cause = document.getElementById(
        "inventory-reason-text"
      );

      const plan = document.getElementById(
        "inventory-reason-plan"
      );

      document.getElementById(
        "inventory-reason-type"
      ).value = item.type;

      cause.name = "nguyen_nhan_" + item.vin;
      plan.name = "phuong_an_" + item.vin;

      cause.value = item.cause || "";
      plan.value = item.plan || "";
    };

    reasonSelect.addEventListener("change", updateReason);
    updateReason();
  }

  // Ghi nhận VIN trong màn hình kiểm đếm.
  const form = document.getElementById("inventory-count-form");

  if (!form) {
    return;
  }

  const rows = Array.from(
    document.querySelectorAll(
      "#inventory-count-table tbody tr[data-vin]"
    )
  );

  const key = "dnf-count-" + form.dataset.countKey;

  let saved = {};

  try {
    saved = JSON.parse(sessionStorage.getItem(key) || "{}");
  } catch {
    saved = {};
  }

  if (
    !saved ||
    typeof saved !== "object" ||
    Array.isArray(saved)
  ) {
    saved = {};
  }

  const vinInput = document.getElementById("inventory-scan-vin");
  const position = document.getElementById(
    "inventory-scan-position"
  );
  const condition = document.getElementById(
    "inventory-scan-condition"
  );
  const note = document.getElementById("inventory-scan-note");
  const error = document.getElementById("inventory-count-error");

  const refresh = () => {
    const records = [];

    rows.forEach(row => {
      const item = saved[row.dataset.vin];

      row.querySelector(
        "[data-count-position]"
      ).textContent = item ? item.position : "Chưa kiểm";

      row.querySelector(
        "[data-count-checked]"
      ).textContent = item ? "Có" : "Chưa";

      if (item) {
        records.push(item);
      }
    });

    document.getElementById(
      "inventory-count-payload"
    ).value = JSON.stringify(records);

    document.getElementById(
      "inventory-count-progress"
    ).textContent =
      `Tiến độ: ${records.length}/${rows.length} xe. ` +
      "Đang lưu tạm trong tab; bấm Hoàn tất kiểm đếm để gửi.";

    try {
      sessionStorage.setItem(key, JSON.stringify(saved));
    } catch {
      // Vẫn giữ bản nháp trong trang hiện tại.
    }
  };

  const recordButton = document.querySelector("[data-record-vin]");

  recordButton.addEventListener("click", () => {
    const vin = vinInput.value.trim();

    const row = rows.find(row => row.dataset.vin === vin);

    if (!vin) {
      error.textContent = "Vui lòng nhập VIN.";
      vinInput.focus();
      return;
    }

    if (!row) {
      error.textContent =
        "VIN chưa thuộc danh sách phiếu. " +
        "Cần kiểm tra riêng xe ngoài danh sách trước khi tiếp tục.";
      return;
    }

    error.textContent = saved[vin]
      ? "VIN đã ghi nhận: cập nhật thông tin, không thêm dòng trùng."
      : "";

    saved[vin] = {
      vin: vin,
      position:
        position.value.trim() || row.dataset.systemPosition,
      condition: condition.value.trim() || "Bình thường",
      note: note.value.trim()
    };

    refresh();

    vinInput.value = "";
    position.value = "";
    note.value = "";

    vinInput.focus();
  });

  vinInput.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      recordButton.click();
    }
  });

  form.addEventListener("submit", event => {
    if (vinInput.value.trim()) {
      event.preventDefault();

      error.textContent =
        "Bấm Ghi nhận VIN cho dòng đang nhập trước khi hoàn tất.";

      return;
    }

    const accepted = confirm(
      "Hoàn tất kiểm đếm? " +
      "Các VIN chưa ghi nhận sẽ được đối chiếu là chưa tìm thấy."
    );

    if (!accepted) {
      event.preventDefault();
    }
  });

  refresh();
})();