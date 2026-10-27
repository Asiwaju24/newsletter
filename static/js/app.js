(function () {
  "use strict";

  // Confirm before destructive or irreversible actions: <form data-confirm="Are you sure?">
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });

  // Copy-to-clipboard buttons: <button data-copy="text">
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var original = button.textContent;
      navigator.clipboard.writeText(button.getAttribute("data-copy")).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = original; }, 1500);
      });
    });
  });

  // Markdown editor with Write / Preview tabs.
  var editor = document.querySelector("[data-editor-root]");
  if (editor) {
    var textarea = editor.querySelector("textarea");
    var preview = editor.querySelector(".preview");
    var tabs = editor.querySelectorAll("[role=tab]");
    var url = editor.getAttribute("data-preview-url");
    var csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;

    function show(name) {
      tabs.forEach(function (tab) { tab.setAttribute("aria-selected", String(tab.dataset.tab === name)); });
      textarea.hidden = name !== "write";
      preview.hidden = name !== "preview";
      if (name === "preview") {
        preview.innerHTML = "<p class='muted'>Loading…</p>";
        var body = new URLSearchParams({ text: textarea.value, csrfmiddlewaretoken: csrf });
        fetch(url, { method: "POST", body: body, headers: { "X-CSRFToken": csrf } })
          .then(function (r) { return r.json(); })
          .then(function (data) { preview.innerHTML = data.html || "<p class='muted'>There's nothing to show yet. Write something first.</p>"; })
          .catch(function () { preview.innerHTML = "<p class='muted'>The preview isn't working right now. Please try again.</p>"; });
      }
    }
    tabs.forEach(function (tab) { tab.addEventListener("click", function () { show(tab.dataset.tab); }); });
  }
})();
