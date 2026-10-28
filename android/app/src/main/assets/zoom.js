/*
 * PleatView zoom for web pages shown as dashboards, such as Grafana or OpenSearch
 * (pleatview.js does this for Home Assistant). Runs at document start, in the top
 * frame only: rewrites the page's viewport so it renders as if the screen were
 * __PLEATVIEW_WIDTH__ CSS pixels wide.
 */
(function () {
  "use strict";
  var width = __PLEATVIEW_WIDTH__;
  if (window.top !== window || !width || location.origin === __PLEATVIEW_HA_ORIGIN__) return;
  var content = "width=" + width;

  function apply() {
    var meta = document.head && document.head.querySelector('meta[name="viewport"]');
    if (!meta) return false;
    if (meta.getAttribute("content") !== content) meta.setAttribute("content", content);
    return true;
  }

  if (apply()) return;
  // Rewrite the page's own viewport tag as soon as the parser creates it, before the
  // page lays out; add one if the page has none.
  var observer = new MutationObserver(function () {
    if (apply()) observer.disconnect();
  });
  observer.observe(document, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", function () {
    observer.disconnect();
    if (!apply() && document.head) {
      var meta = document.createElement("meta");
      meta.name = "viewport";
      meta.content = content;
      document.head.appendChild(meta);
    }
  });
})();
