/**
 * Load MathJax asynchronously so it doesn't block first paint.
 *
 * mkdocs.yml's `extra_javascript` injects each entry as a synchronous
 * <script src="..."></script> in <head>. MathJax v3 is ~5 MB, and rendering
 * formulas is never critical to first paint (they're below the fold and
 * readers don't read them for several seconds anyway).
 *
 * This loader is loaded synchronously (it's tiny) and injects MathJax with
 * async=true, so the browser fetches it without blocking the HTML parser.
 *
 * The MathJax config object (window.MathJax) MUST be set before the script
 * is injected — that's why we set it here, not rely on MathJax's defaults.
 */
(function () {
  // Don't double-inject (e.g. after a SPA navigation that re-runs extras).
  if (window.__mathjaxInjected) return;
  window.__mathjaxInjected = true;

  window.MathJax = {
    tex: {
      inlineMath: [["\\(", "\\)"]],
      displayMath: [["\\[", "\\]"]],
      processEscapes: true,
      processRefs: true,
    },
    options: {
      skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"],
    },
    svg: { fontCache: "global" },
  };

  var s = document.createElement("script");
  s.src = "https://unpkg.com/mathjax@3/es5/tex-mml-chtml.js";
  s.async = true;
  document.head.appendChild(s);
})();
