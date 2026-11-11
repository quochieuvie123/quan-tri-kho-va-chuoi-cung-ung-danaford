function khoiTaoDropdown(khung) {
    if (khung.dataset.daKhoiTao === "true") {
        return;
    }

    const oChon = khung.querySelector("select");
    const nutMo = khung.querySelector(".nut-chon-kho");
    const tenDaChon = nutMo.querySelector("span");
    const danhSach = khung.querySelector(".danh-sach-kho");
    const cacNut = [];

    const nhan = document.querySelector(
        'label[for="' + oChon.id + '"]'
    );

    let tenTruong = "Lựa chọn";

    if (nhan) {
        tenTruong = nhan.textContent.trim();
    }

    if (!nutMo.id) {
        nutMo.id = oChon.id + "-nut";
    }

    if (!danhSach.id) {
        danhSach.id = oChon.id + "-danh-sach";
    }

    nutMo.setAttribute("aria-controls", danhSach.id);
    danhSach.setAttribute("aria-label", tenTruong);

    function capNhatHienThi() {
        if (oChon.selectedIndex >= 0) {
            tenDaChon.textContent =
                oChon.options[oChon.selectedIndex].text;
        } else {
            tenDaChon.textContent =
                "Chọn " + tenTruong.toLowerCase();
        }

        nutMo.setAttribute(
            "aria-label",
            tenTruong + " " + tenDaChon.textContent
        );

        cacNut.forEach(function (nut) {
            nut.setAttribute(
                "aria-selected",
                String(nut.dataset.value === oChon.value)
            );
        });
    }

    function dongDanhSach() {
        danhSach.hidden = true;
        nutMo.setAttribute("aria-expanded", "false");
    }

    function moDanhSach() {
        danhSach.hidden = false;
        nutMo.setAttribute("aria-expanded", "true");

        let nutCanFocus = danhSach.querySelector(
            '[aria-selected="true"]:not(:disabled)'
        );

        if (!nutCanFocus) {
            nutCanFocus = danhSach.querySelector(
                "button:not(:disabled)"
            );
        }

        if (nutCanFocus) {
            nutCanFocus.focus();
        }
    }

    for (const luaChon of oChon.options) {
        const nut = document.createElement("button");

        nut.type = "button";
        nut.className = "lua-chon-kho";
        nut.dataset.value = luaChon.value;
        nut.textContent = luaChon.text;
        nut.disabled = luaChon.disabled;
        nut.tabIndex = -1;

        nut.setAttribute("role", "option");

        nut.addEventListener("click", function () {
            if (oChon.value !== nut.dataset.value) {
                oChon.value = nut.dataset.value;

                oChon.dispatchEvent(
                    new Event("change", { bubbles: true })
                );
            }

            dongDanhSach();
            nutMo.focus();
        });

        danhSach.appendChild(nut);
        cacNut.push(nut);
    }

    nutMo.addEventListener("click", function () {
        if (danhSach.hidden) {
            moDanhSach();
        } else {
            dongDanhSach();
        }
    });

    nutMo.addEventListener("keydown", function (event) {
        if (
            event.key === "ArrowDown" ||
            event.key === "ArrowUp"
        ) {
            event.preventDefault();
            moDanhSach();
        }
    });

    danhSach.addEventListener("keydown", function (event) {
        const cacNutBat = cacNut.filter(function (nut) {
            return !nut.disabled;
        });

        if (cacNutBat.length === 0) {
            return;
        }

        let viTri = cacNutBat.indexOf(document.activeElement);

        if (event.key === "ArrowDown") {
            event.preventDefault();

            viTri = (viTri + 1) % cacNutBat.length;
            cacNutBat[viTri].focus();

        } else if (event.key === "ArrowUp") {
            event.preventDefault();

            viTri = (
                viTri - 1 + cacNutBat.length
            ) % cacNutBat.length;

            cacNutBat[viTri].focus();

        } else if (event.key === "Home") {
            event.preventDefault();
            cacNutBat[0].focus();

        } else if (event.key === "End") {
            event.preventDefault();
            cacNutBat[cacNutBat.length - 1].focus();

        } else if (event.key === "Escape") {
            event.preventDefault();

            dongDanhSach();
            nutMo.focus();

        } else if (event.key === "Tab") {
            dongDanhSach();
            nutMo.focus();
        }
    });

    document.addEventListener("click", function (event) {
        if (!khung.contains(event.target)) {
            dongDanhSach();
        }
    });

    khung.addEventListener("focusout", function (event) {
        if (!khung.contains(event.relatedTarget)) {
            dongDanhSach();
        }
    });

    oChon.addEventListener("change", capNhatHienThi);

    capNhatHienThi();

    for (const thuocTinh of ["aria-invalid", "aria-describedby"]) {
        if (oChon.hasAttribute(thuocTinh)) {
            nutMo.setAttribute(
                thuocTinh,
                oChon.getAttribute(thuocTinh)
            );
        }
    }

    nutMo.disabled = (
        oChon.disabled ||
        !danhSach.querySelector("button:not(:disabled)")
    );

    oChon.hidden = true;
    nutMo.hidden = false;

    if (nhan) {
        nhan.htmlFor = nutMo.id;
    }

    khung.dataset.daKhoiTao = "true";
}

document.querySelectorAll(
    ".giao-dien-dnf .chon-kho"
).forEach(khoiTaoDropdown);
