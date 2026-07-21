// Language switcher: populates header-bar tab buttons, rewrites URLs across
// editions, and updates the left sidebar navigation links to follow.
//
// URL mapping rules (from mkdocs.yml → extra.languages):
//   zh: book/chapter1.md        (default, no suffix)
//   en: book-en/chapter1.md
//   ta: book-ta/chapter1.ta.md  (.ta suffix before .md)
//   vi: book-vi/chapter1.vi.md  (.vi suffix before .md)

(function () {
  "use strict";

  var cfg = window.config.extra && window.config.extra.languages;
  if (!cfg) return;

  // ── helpers ───────────────────────────────────────────────

  function detectLang(path) {
    var p = path.replace(/\/$/, "");
    for (var code in cfg) {
      if (cfg.hasOwnProperty(code) && p.indexOf(cfg[code].prefix) !== -1)
        return code;
    }
    var def = null;
    for (var c in cfg) {
      if (cfg.hasOwnProperty(c) && cfg[c].default) { def = c; break; }
    }
    return def || "zh";
  }

  function mapUrl(currentPath, targetCode) {
    if (targetCode === activeLang) return null;
    var src = cfg[activeLang];
    var dst = cfg[targetCode];
    var url = currentPath.replace(src.prefix, dst.prefix);
    if (src.suffix) url = url.replace(src.suffix + ".md", ".md");
    if (dst.suffix) url = url.replace(/\.md$/, dst.suffix + ".md");
    return url || dst.prefix + "introduction" + (dst.suffix || "") + ".md";
  }

  // ── sidebar rewriting ─────────────────────────────────────

  function rewriteSidebar(targetCode) {
    var target = cfg[targetCode];
    var defCode = null;
    for (var c in cfg) { if (cfg.hasOwnProperty(c) && cfg[c].default) { defCode = c; break; } }
    defCode = defCode || "zh";
    var defCfg = cfg[defCode];

    var links = document.querySelectorAll(".md-nav__link");
    for (var i = 0; i < links.length; i++) {
      var el = links[i];
      var href = el.getAttribute("href");
      if (!href || href.indexOf("http") === 0 || href.charAt(0) === "#") continue;
      href = href.replace(/^\//, "");

      var defPrefix = (defCfg.prefix || "").replace(/\/$/, "");
      var tgtPrefix = (target.prefix || "").replace(/\/$/, "");

      if (defPrefix && href.indexOf(defPrefix) === 0) {
        href = tgtPrefix + href.slice(defPrefix.length);
      }
      var defSuf = defCfg.suffix || "";
      var tgtSuf = target.suffix || "";
      if (defSuf) href = href.replace(defSuf + ".html", ".html");
      if (tgtSuf && href.indexOf(".html") !== -1) {
        href = href.replace(/\.html$/, tgtSuf + ".html");
      }
      el.setAttribute("href", "/" + href);
    }
  }

  // ── render ────────────────────────────────────────────────

  function render() {
    var path = location.pathname;
    var activeLang = detectLang(path);
    var container = document.getElementById("lang-tabs-root");
    if (!container) return;

    // Skip if already populated.
    if (container.children.length > 0) return;

    var codes = Object.keys(cfg);
    for (var idx = 0; idx < codes.length; idx++) {
      var code = codes[idx];
      var lang = cfg[code];
      var btn = document.createElement("button");
      btn.className =
        "lang-tab" + (code === activeLang ? " lang-tab--active" : "");
      btn.textContent = lang.label;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected",
                       String(code === activeLang));

      (function (tgtCode) {
        btn.addEventListener("click", function () {
          if (tgtCode === activeLang) return;
          var target = mapUrl(path, tgtCode);
          if (target) location.href = target;
        });
      })(code);

      container.appendChild(btn);
    }

    // Rewrite sidebar for non-default languages.
    var defCode = null;
    for (var c in cfg) {
      if (cfg.hasOwnProperty(c) && cfg[c].default) { defCode = c; break; }
    }
    if (activeLang !== (defCode || "zh")) {
      rewriteSidebar(activeLang);
    }
  }

  // ── bootstrap ──────────────────────────────────────────────

  function boot() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", render);
    } else {
      render();
    }
    // Re-render on SPA instant-navigation.
    document.addEventListener("locationchange", render);
    var _pushState = history.pushState;
    history.pushState = function () {
      _pushState.apply(this, arguments);
      setTimeout(render, 60);
    };
  }

  boot();
})();
