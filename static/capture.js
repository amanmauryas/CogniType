(function () {
  const $ = id => document.getElementById(id);
  const area = $("typing"), finish = $("finish"), panel = $("effort-panel"), send = $("send");
  const active = {}, keys = []; let t0 = null;
  // Block paste/drop so every character comes from real keystrokes.
  ["paste", "drop", "contextmenu", "copy", "cut"].forEach(ev => area.addEventListener(ev, e => e.preventDefault()));
  area.addEventListener("keydown", e => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = performance.now(); if (t0 === null) t0 = t;
    active[e.code] = t - t0;
  });
  area.addEventListener("keyup", e => {
    if (active[e.code] === undefined) return;
    keys.push({ c: e.code, p: active[e.code], r: performance.now() - t0 });
    delete active[e.code];
  });
  finish.addEventListener("click", () => {
    if (keys.length < 40) { alert("Please type the whole passage before finishing."); return; }
    area.disabled = true; finish.hidden = true; panel.hidden = false;
  });
  send.addEventListener("click", () => {
    const v = document.querySelector("input[name=effort]:checked");
    if (!v) { alert("Please rate your mental effort first."); return; }
    send.disabled = true;
    fetch(area.dataset.endpoint, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys, typed: area.value, effort: +v.value }) })
      .then(r => { if (!r.ok) throw 0; return r.json(); })
      .then(d => location.href = d.next)
      .catch(() => { alert("Could not save. Please try again."); send.disabled = false; });
  });
})();
