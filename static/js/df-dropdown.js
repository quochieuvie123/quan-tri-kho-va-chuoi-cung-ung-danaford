(function () {
  "use strict";

  var ACTIVE_INSTANCE = null;

  function closeActive() {
    if (ACTIVE_INSTANCE) {
      ACTIVE_INSTANCE.close();
      ACTIVE_INSTANCE = null;
    }
  }

  function isHiddenWrapper(select) {
    var el = select;
    while (el && el !== document.body) {
      var st = window.getComputedStyle(el);
      if (st.display === "none") return true;
      el = el.parentElement;
    }
    return false;
  }

  function resolveVariantClass(select) {
    if (select.closest(".bc")) return "df-dropdown__trigger--45";
    if (select.closest(".transfer-search-form") || select.closest(".transfer-page-container")) {
      return "df-dropdown__trigger--44";
    }
    return "";
  }

  function enhanceSelect(select) {
    if (select.dataset.dfDropdownReady === "1") return;
    if (select.multiple || select.hasAttribute("data-df-native")) return;
    if (isHiddenWrapper(select)) return;

    select.dataset.dfDropdownReady = "1";

    var wrap = document.createElement("div");
    wrap.className = "df-dropdown";

    var inlineMinWidth = select.style.minWidth;
    var inlineMaxWidth = select.style.maxWidth;
    var inlineWidth = select.style.width;
    if (inlineMinWidth) wrap.style.minWidth = inlineMinWidth;
    if (inlineMaxWidth) wrap.style.maxWidth = inlineMaxWidth;
    if (inlineWidth && inlineWidth !== "100%") wrap.style.width = inlineWidth;

    var parent = select.parentNode;
    parent.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("df-dropdown__native");
    select.tabIndex = -1;

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "df-dropdown__trigger " + resolveVariantClass(select);
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    if (select.disabled) trigger.disabled = true;

    var labelSpan = document.createElement("span");
    labelSpan.className = "df-dropdown__label";
    var chevron = document.createElement("span");
    chevron.className = "df-dropdown__chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.innerHTML =
      '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 6L8 10L12 6" stroke="#627D98" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    trigger.appendChild(labelSpan);
    trigger.appendChild(chevron);
    wrap.appendChild(trigger);

    var portal = null;
    var focusedIndex = -1;
    var typeBuffer = "";
    var typeTimer = null;

    function syncLabel() {
      var opt = select.options[select.selectedIndex];
      labelSpan.textContent = opt ? opt.textContent.trim() : "";
      trigger.disabled = !!select.disabled;
      if (select.id) {
        trigger.setAttribute("data-for-id", select.id);
      }
    }

    function getVisibleOptions() {
      var list = [];
      for (var i = 0; i < select.options.length; i++) {
        var o = select.options[i];
        if (!o.hidden) {
          list.push({ index: i, option: o });
        }
      }
      return list;
    }

    function positionPortal() {
      if (!portal) return;
      var rect = trigger.getBoundingClientRect();
      var vw = document.documentElement.clientWidth;
      var vh = window.innerHeight;
      var width = Math.max(rect.width, 160);
      if (width > vw - 16) width = vw - 16;

      var left = rect.left;
      if (left + width > vw - 8) left = Math.max(8, vw - width - 8);
      if (left < 8) left = 8;

      portal.style.width = width + "px";
      portal.style.left = left + "px";
      portal.style.maxHeight = "252px";

      var naturalH = Math.min(portal.scrollHeight, 252);
      var spaceBelow = vh - rect.bottom - 8;
      var spaceAbove = rect.top - 8;

      if (spaceBelow >= Math.min(naturalH, 140) || spaceBelow >= spaceAbove) {
        portal.style.top = rect.bottom + 4 + "px";
        portal.style.bottom = "auto";
        if (spaceBelow < 252) {
          portal.style.maxHeight = Math.max(100, spaceBelow) + "px";
        }
      } else {
        portal.style.top = "auto";
        portal.style.bottom = vh - rect.top + 4 + "px";
        if (spaceAbove < 252) {
          portal.style.maxHeight = Math.max(100, spaceAbove) + "px";
        }
      }
    }

    function renderOptions() {
      if (!portal) return;
      portal.innerHTML = "";
      var visible = getVisibleOptions();
      focusedIndex = -1;

      visible.forEach(function (entry, pos) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "df-dropdown__option";
        btn.setAttribute("role", "option");
        btn.textContent = entry.option.textContent.trim();

        var isSelected = entry.index === select.selectedIndex;
        var isDisabled = !!entry.option.disabled;

        if (isSelected) {
          btn.classList.add("is-selected");
          btn.setAttribute("aria-selected", "true");
          focusedIndex = pos;
        } else {
          btn.setAttribute("aria-selected", "false");
        }

        if (isDisabled) {
          btn.classList.add("is-disabled");
          btn.disabled = true;
        } else {
          btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            chooseOption(entry.index);
          });
        }

        portal.appendChild(btn);
      });
    }

    function updateFocusedVisual() {
      if (!portal) return;
      var btns = portal.querySelectorAll(".df-dropdown__option");
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle("is-focused", i === focusedIndex);
      }
      if (focusedIndex >= 0 && btns[focusedIndex]) {
        btns[focusedIndex].scrollIntoView({ block: "nearest" });
      }
    }

    function chooseOption(idx) {
      var prev = select.selectedIndex;
      select.selectedIndex = idx;
      syncLabel();
      close();
      trigger.focus();
      if (prev !== idx) {
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    function open() {
      if (select.disabled) return;
      if (ACTIVE_INSTANCE && ACTIVE_INSTANCE !== instance) {
        ACTIVE_INSTANCE.close();
      }
      if (portal) return;

      portal = document.createElement("div");
      portal.className = "df-dropdown-portal";
      portal.setAttribute("role", "listbox");

      var activeDialog = select.closest("dialog[open]");
      (activeDialog || document.body).appendChild(portal);

      renderOptions();
      positionPortal();
      updateFocusedVisual();
      trigger.setAttribute("aria-expanded", "true");
      ACTIVE_INSTANCE = instance;
    }

    function close() {
      if (!portal) return;
      if (portal.parentNode) portal.parentNode.removeChild(portal);
      portal = null;
      trigger.setAttribute("aria-expanded", "false");
      if (ACTIVE_INSTANCE === instance) ACTIVE_INSTANCE = null;
    }

    var instance = { close: close };

    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (portal) close();
      else open();
    });

    trigger.addEventListener("keydown", function (e) {
      if (select.disabled) return;
      if (e.key === "Escape") {
        if (portal) {
          e.preventDefault();
          close();
        }
        return;
      }
      if (e.key === "Tab") {
        close();
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!portal) {
          open();
          return;
        }
        var btns = portal.querySelectorAll(".df-dropdown__option:not(.is-disabled)");
        if (!btns.length) return;
        var allBtns = Array.prototype.slice.call(portal.querySelectorAll(".df-dropdown__option"));
        var step = e.key === "ArrowDown" ? 1 : -1;
        var next = focusedIndex;
        for (var tries = 0; tries < allBtns.length; tries++) {
          next = (next + step + allBtns.length) % allBtns.length;
          if (!allBtns[next].disabled) {
            focusedIndex = next;
            updateFocusedVisual();
            break;
          }
        }
        return;
      }
      if (e.key === "Enter" || e.key === " ") {
        if (portal && focusedIndex >= 0) {
          e.preventDefault();
          var visible = getVisibleOptions();
          if (visible[focusedIndex] && !visible[focusedIndex].option.disabled) {
            chooseOption(visible[focusedIndex].index);
          }
        } else if (!portal) {
          e.preventDefault();
          open();
        }
        return;
      }
      if (e.key && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        typeBuffer += e.key.toLowerCase();
        clearTimeout(typeTimer);
        typeTimer = setTimeout(function () {
          typeBuffer = "";
        }, 550);
        var visibleOpts = getVisibleOptions();
        for (var k = 0; k < visibleOpts.length; k++) {
          if (
            !visibleOpts[k].option.disabled &&
            visibleOpts[k].option.textContent.trim().toLowerCase().indexOf(typeBuffer) === 0
          ) {
            if (portal) {
              focusedIndex = k;
              updateFocusedVisual();
            } else {
              chooseOption(visibleOpts[k].index);
            }
            break;
          }
        }
      }
    });

    select.addEventListener("change", syncLabel);
    select.addEventListener("invalid", function () {
      trigger.focus();
    });

    if (select.form) {
      select.form.addEventListener("reset", function () {
        setTimeout(syncLabel, 0);
      });
    }

    if (select.id) {
      var assocLabels = document.querySelectorAll('label[for="' + CSS.escape(select.id) + '"]');
      assocLabels.forEach(function (lbl) {
        lbl.addEventListener("click", function (e) {
          e.preventDefault();
          trigger.focus();
        });
      });
    }

    var obs = new MutationObserver(function () {
      syncLabel();
      if (portal) renderOptions();
    });
    obs.observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled", "hidden", "selected"]
    });

    syncLabel();
  }

  function initDropdowns() {
    var selects = document.querySelectorAll("main.df-content select");
    for (var i = 0; i < selects.length; i++) {
      enhanceSelect(selects[i]);
    }
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".df-dropdown") && !e.target.closest(".df-dropdown-portal")) {
      closeActive();
    }
  });

  window.addEventListener("resize", closeActive);
  window.addEventListener("scroll", function (e) {
    if (ACTIVE_INSTANCE && e.target && e.target.closest && e.target.closest(".df-dropdown-portal")) {
      return;
    }
    closeActive();
  }, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDropdowns);
  } else {
    initDropdowns();
  }
})();
