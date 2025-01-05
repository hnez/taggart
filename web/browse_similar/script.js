"use strict";

import { get_json, post_json, put_json } from "/common.js";

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
  await put_json(`/images/${image_id}/tags/${tag_name}`, { assigned: weight });
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
  const tags = await get_json(`/images/${id}/tags`);

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

    if ("estimated" in meta) {
      tags_estimated.push(meta);
    }
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

function roster_img_elem(id) {
  const img = document.createElement("img");
  img.className = "roster-element";
  img.src = `/images/${id}.jpg`;
  img.loading = "lazy";

  const a = document.createElement("a");
  a.href = `#${id}`;
  a.append(img);

  return a;
}

async function populate_roster(id) {
  const roster_elem = document.querySelector("#roster");

  const neighbors = await get_json(`/images/${id}/neighbors`);

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
  // This is a slow operation, hence why we do the two roster updated
  // in two steps.
  const similar = await get_json(`/images/${id}/similar`);

  for (const idx_sim of similar.images.reverse()) {
    roster_elem.append(roster_img_elem(idx_sim[0]));
  }
}

async function load_image(id) {
  // Populate the main image
  document.querySelector("#main").src = `/images/${id}.jpg`;
  document.querySelector("#latent-image").src =
    `/images/${id}/latent/preview.png`;

  reset_crop_box();
  await populate_tag_editor(id);
  await populate_roster(id);
}

function reset_crop_box() {
  const crop_box = document.querySelector("#crop-box");

  crop_box.style.left = "";
  crop_box.style.top = "";
  crop_box.style.right = "";
  crop_box.style.bottom = "";
}

function update_crop_box(mouse_ev) {
  const crop_editor = document.querySelector("#crop-editor");
  const crop_box = document.querySelector("#crop-box");

  const ce_bb = crop_editor.getBoundingClientRect();
  const cb_bb = crop_box.getBoundingClientRect();

  let left = cb_bb.left - ce_bb.left;
  let right = ce_bb.right - cb_bb.right;

  const off_left = mouse_ev.clientX - ce_bb.left;
  const off_right = ce_bb.right - mouse_ev.clientX;

  if (left === 0) {
    left = off_left;
  } else if (right === 0) {
    right = off_right;
  } else if (Math.abs(off_left - left) < Math.abs(off_right - right)) {
    left = off_left;
  } else {
    right = off_right;
  }

  let bottom = ce_bb.bottom - cb_bb.bottom;
  let top = cb_bb.top - ce_bb.top;

  const off_top = mouse_ev.clientY - ce_bb.top;
  const off_bottom = ce_bb.bottom - mouse_ev.clientY;

  if (top === 0) {
    top = off_top;
  } else if (bottom === 0) {
    bottom = off_bottom;
  } else if (Math.abs(off_top - top) < Math.abs(off_bottom - bottom)) {
    top = off_top;
  } else {
    bottom = off_bottom;
  }

  crop_box.style.left = `${left}px`;
  crop_box.style.top = `${top}px`;
  crop_box.style.right = `${right}px`;
  crop_box.style.bottom = `${bottom}px`;
}

async function add_crop(mouse_ev, image_id) {
  mouse_ev.stopPropagation();

  const image = document.querySelector("#main");
  const im_bb = image.getBoundingClientRect();
  const res_width = image.naturalWidth;
  const res_height = image.naturalHeight;

  let scaling_factor;
  let offset_x = 0;
  let offset_y = 0;

  if (res_width * im_bb.height < res_height * im_bb.width) {
    // Scaling is limited in the height dimension and the image is centered vertically.
    scaling_factor = res_height / im_bb.height;
    offset_x = (im_bb.width * scaling_factor - res_width) / 2;
  } else {
    // Scaling is limited in the width dimension and the image is centered horizontally.
    scaling_factor = res_width / im_bb.width;
    offset_y = (im_bb.height * scaling_factor - res_height) / 2;
  }

  const crop_box = document.querySelector("#crop-box");
  const cb_bb = crop_box.getBoundingClientRect();

  const crop = {
    height: cb_bb.height * scaling_factor,
    left: (cb_bb.left - im_bb.left) * scaling_factor - offset_x,
    top: (cb_bb.top - im_bb.top) * scaling_factor - offset_y,
    width: cb_bb.width * scaling_factor,
  };

  reset_crop_box();

  const _image_url = await post_json(`/images/${image_id}/crops`, crop);

  // TODO: do something with the URL
}

async function main() {
  // eslint-disable-next-line no-console
  console.log("OK let's go!");

  let image_id = 1;

  // Set the initial image based on the URL anchor (if there is one).
  if (window.location.hash) {
    const hash = window.location.hash;
    image_id = Number(hash.slice(1));
  }

  // Change the active image based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    image_id = Number(hash.slice(1));

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

  const crop_editor = document.querySelector("#crop-editor");
  crop_editor.addEventListener("mouseup", update_crop_box);

  const crop_button = document.querySelector("#crop-button");
  crop_button.addEventListener("mouseup", (ev) => add_crop(ev, image_id));

  await load_image(image_id);
}

window.addEventListener("load", main);
