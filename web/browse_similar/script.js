"use strict";

import { cropped_image, get_json, put_json } from "/common.js";

function tag_elem(image_id, tag_name, weight, where) {
  weight = Math.min(Math.max(weight, -1), 1);
  weight = (1 - weight) / 2;

  const hue = Math.floor(147 * (1 - weight));

  const label = document.createElement("span");
  label.className = "tag-label";
  label.textContent = tag_name;
  label.style.backgroundColor = `hsl(${hue}, 100%, 50%)`;

  if (where === "suggested") {
    label.addEventListener("click", (ev) =>
      set_tag_weight(image_id, tag_name, ev.shiftKey ? -1 : 1),
    );
  } else {
    label.addEventListener("click", (_ev) =>
      set_tag_weight(image_id, tag_name, 0),
    );
  }

  const detail = document.createElement("a");
  detail.className = "tag-detail";
  detail.textContent = "🔍";
  detail.href = `/browse_tags/#${tag_name}`;

  const tag = document.createElement("span");
  tag.className = "tag";
  tag.append(label);
  tag.append(detail);

  return tag;
}

async function set_tag_weight(image_id, tag_name, weight) {
  await put_json(`/api/images/${image_id}/tags/${tag_name}`, {
    assigned: weight,
  });
  await populate_tag_editor(image_id);
}

function filter_suggested_tags() {
  const textbox_elem = document.querySelector("#tags-textbox");
  const filter = textbox_elem.value.toLowerCase().trim();
  const tags_suggested_div = document.querySelector("#tags-suggested");
  const tags = tags_suggested_div.querySelectorAll(".tag");

  for (const tag_elem of tags) {
    const tag_name = tag_elem.textContent;
    const hide = !tag_name.includes(filter);

    tag_elem.classList.remove("hidden");

    if (hide) {
      tag_elem.classList.add("hidden");
    }
  }
}

async function populate_tag_editor(id) {
  const tags = await get_json(`/api/images/${id}/tags`);

  const tags_assigned_pos = [];
  const tags_assigned_neg = [];
  const tags_estimated = [];

  for (const [name, meta] of Object.entries(tags)) {
    meta["name"] = name;

    if ("assigned" in meta) {
      if (meta["assigned"] > 0) tags_assigned_pos.push(meta);
      if (meta["assigned"] < 0) tags_assigned_neg.push(meta);
      continue;
    }

    if (!("estimated" in meta)) {
      meta["estimated"] = -1;
    }

    tags_estimated.push(meta);
  }

  tags_assigned_pos.sort((a, b) => a["name"] > b["name"]);
  tags_assigned_neg.sort((a, b) => a["name"] > b["name"]);

  tags_estimated.sort((a, b) => a["estimated"] < b["estimated"]);

  document
    .querySelector("#tags-assigned-positive")
    .replaceChildren(
      ...tags_assigned_pos.map((meta) =>
        tag_elem(id, meta.name, meta.assigned, "assigned"),
      ),
    );

  document
    .querySelector("#tags-assigned-negative")
    .replaceChildren(
      ...tags_assigned_neg.map((meta) =>
        tag_elem(id, meta.name, meta.assigned, "assigned"),
      ),
    );

  document
    .querySelector("#tags-suggested")
    .replaceChildren(
      ...tags_estimated.map((meta) =>
        tag_elem(id, meta.name, meta.estimated, "suggested"),
      ),
    );

  filter_suggested_tags();
}

function roster_img_elem(info) {
  const a = document.createElement("a");
  a.className = "roster-element";

  if (info) {
    const img = cropped_image(info);
    a.append(img);
    a.href = `#${info.id}`;
  }

  return a;
}

async function populate_roster(id) {
  const roster_elem = document.querySelector("#roster");

  const neighbors = await get_json(`/api/images/${id}/neighbors`);

  // Populate the roster of other images
  // Start with the next, previous, a shuffled next and shuffled previous
  // image.
  roster_elem.replaceChildren(
    roster_img_elem(neighbors.serial_prev),
    roster_img_elem(neighbors.serial_next),
    roster_img_elem(neighbors.shuffle_prev),
    roster_img_elem(neighbors.shuffle_next),
  );

  // Then add images that the server deemed similar to this one.
  // This is a slow operation, hence why we do the two roster update
  // in two steps.
  const similar = await get_json(`/api/images/${id}/similar`);

  for (const idx_sim of similar.images.sort((a, b) => a[1] < b[1])) {
    roster_elem.append(roster_img_elem(idx_sim[0]));
  }
}

async function load_image(id) {
  const info = await get_json(`/api/images/${id}`);

  document.querySelector("#latent-image").src = info.latent_url || "";

  const pane_center = document.querySelector("#pane-center");
  pane_center.replaceChildren(cropped_image(info, true));

  await populate_tag_editor(id);
  await populate_roster(id);
}

async function main() {
  // eslint-disable-next-line no-console
  console.log("OK let's go!");

  let image_id;

  // Set the initial image based on the URL anchor (if there is one).
  if (window.location.hash) {
    const hash = window.location.hash;
    image_id = hash.slice(1);
  } else {
    const info = await get_json(`/api/images/random`);
    image_id = info.id;
  }

  // Change the active image based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    image_id = url.hash.slice(1);

    load_image(image_id);
  });

  // Make the tag textbox interactive
  const tags_textbox = document.querySelector("#tags-textbox");
  tags_textbox.addEventListener("input", (_ev) => filter_suggested_tags());
  tags_textbox.addEventListener("keyup", (ev) => {
    if (ev.key === "Enter") {
      const name = ev.target.value.trim().toLowerCase();

      set_tag_weight(image_id, name, 1);
      ev.target.value = "";

      filter_suggested_tags();
    }
  });

  await load_image(image_id);
}

window.addEventListener("load", main);
