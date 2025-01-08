"use strict";

import { cropped_image, get_json } from "/common.js";

function get_filter() {
  const hash = window.location.hash;

  if (!hash) {
    return [];
  }

  const tags = hash.slice(1).split("+").map(decodeURIComponent);

  return tags;
}

function populate_filter_elem() {
  const tags = get_filter();

  const filter_elem = document.querySelector("#tags-filter");
  filter_elem.innerHTML = "";

  for (const tag_name of tags) {
    const span = document.createElement("span");
    span.textContent = tag_name;
    span.className = "tag";
    span.addEventListener("click", (_ev) => remove_tag_from_filter(tag_name));

    filter_elem.append(span);
  }
}

function set_filter(tags) {
  window.location.hash = tags.map(encodeURIComponent).join("+");
  populate_filter_elem();
}

function add_tag_to_filter(tag_name) {
  const tags = get_filter();

  if (tags.includes(tag_name)) {
    return;
  }

  tags.push(tag_name);

  set_filter(tags);
}

function remove_tag_from_filter(tag_name) {
  const tags = get_filter();
  const tag_index = tags.indexOf(tag_name);

  if (tag_index === -1) {
    return;
  }

  tags.splice(tag_index, 1);

  set_filter(tags);
}

async function load_tag_list() {
  const tags = await get_json("/api/tags");

  const tag_elems = Object.entries(tags)
    .toSorted((nma, nmb) => nma[1]["occurrences"] < nmb[1]["occurrences"])
    .map((name_meta) => {
      const tag = name_meta[0];
      const span = document.createElement("span");
      span.textContent = tag;
      span.className = "tag";
      span.addEventListener("click", (_ev) => add_tag_to_filter(tag));

      return span;
    });

  document.querySelector("#tags-available").replaceChildren(...tag_elems);
}

async function load_image_list(filter) {
  let images = [];

  if (filter) {
    const json = await get_json(
      `/api/tags/${filter}/images?assigned=false&estimated=true`,
    );

    images = json.images;
  }

  const page_elems = [];

  for (let i = 0; ; i += 1) {
    const page_images = images.slice(i * 6, (i + 1) * 6);

    if (page_images.length === 0) break;

    const page_elem = document.createElement("div");
    page_elem.className = "page";

    for (const image of page_images) {
      const img = cropped_image(image.info);

      const a = document.createElement("a");
      a.href = `/browse_similar/#${image.info.id}`;
      a.append(img);

      const tile = document.createElement("div");
      tile.className = "tile";
      tile.append(a);

      page_elem.append(tile);
    }

    page_elems.push(page_elem);
  }

  document.querySelector("#pages").replaceChildren(...page_elems);
}

async function main() {
  // eslint-disable-next-line no-console
  console.log("OK let's go!");

  // Change the active tag based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    const filter = hash.slice(1);

    load_image_list(filter);
  });

  if (window.location.hash) {
    const hash = window.location.hash;
    const filter = hash.slice(1);

    load_image_list(filter);
    populate_filter_elem();
  }

  await load_tag_list();
}

window.addEventListener("load", main);
