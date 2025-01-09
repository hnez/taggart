"use strict";

import { get_json } from "/common.js";

async function populate_trace_table() {
  const statistics = await get_json("/api/statistics");

  const rows = [];
  let max_duration = 1;

  for (const name of Object.keys(statistics.durations)) {
    rows.push({
      calls: statistics.calls[name],
      duration: statistics.durations[name],
      name: name,
    });

    max_duration = Math.max(max_duration, statistics.durations[name]);
  }

  rows.sort((a, b) => a.duration < b.duration);

  const table = document.querySelector("#traces");

  // Copy over the header
  const header = table.querySelector("tr");
  const row_elems = [header];

  for (const row of rows) {
    const total_duration = (row.duration / 1e9).toFixed(3);
    const per_call_duration = (row.duration / row.calls / 1e6).toFixed(3);

    const tr = document.createElement("tr");

    const td_name = document.createElement("td");
    td_name.textContent = row.name;
    tr.append(td_name);

    const td_total_duration = document.createElement("td");
    td_total_duration.textContent = `${total_duration} s`;
    tr.append(td_total_duration);

    const td_calls = document.createElement("td");
    td_calls.textContent = row.calls;
    tr.append(td_calls);

    const td_call_duration = document.createElement("td");
    td_call_duration.textContent = `${per_call_duration} ms`;
    tr.append(td_call_duration);

    row_elems.push(tr);
  }

  table.replaceChildren(...row_elems);
}

async function main() {
  // eslint-disable-next-line no-console
  console.log("OK let's go!");

  await populate_trace_table();
}

window.addEventListener("load", main);
