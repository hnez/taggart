"use strict";

var images = null;
var page_elements = [];

function get_filter() {
  const hash = window.location.hash;

  if (!hash) {
    return [];
  }

  const tags = hash.substring(1).split("+").map(decodeURIComponent);

  return tags;
}

function populate_filter_elem() {
  const tags = get_filter();

  const filter_elem = document.getElementById("tags-filter");
  filter_elem.innerHTML = "";

  for (let tag_name of tags) {
    let span = document.createElement("span");
    span.innerText = tag_name;
    span.className = "tag";
    span.onclick = (_ev) => remove_tag_from_filter(tag_name);

    filter_elem.appendChild(span);
  }
}

function set_filter(tags) {
  window.location.hash = tags.map(encodeURIComponent).join("+");
  populate_filter_elem();
}

function add_tag_to_filter(tag_name) {
  let tags = get_filter();

  if (tags.includes(tag_name)) {
    return;
  }

  tags.push(tag_name);

  set_filter(tags);
}

function remove_tag_from_filter(tag_name) {
  let tags = get_filter();
  const tag_index = tags.indexOf(tag_name);

  if (tag_index < 0) {
    return;
  }

  tags.splice(tag_index, 1);

  set_filter(tags);
}

async function load_tag_list() {
  const response = await fetch(`/tags.json`);
  const json = await response.json();
  const tags = json.tags;

  const available_elem = document.getElementById("tags-available");

  available_elem.innerHTML = "";

  for (let tag of tags) {
    let tag_name = tag[0];

    let span = document.createElement("span");
    span.innerText = tag_name;
    span.className = "tag";
    span.onclick = (_ev) => add_tag_to_filter(tag_name);

    available_elem.appendChild(span);
  }
}

async function load_image_list(filter) {
  if (filter) {
    const response = await fetch(`/tag/${filter}/images/by_embedding.json`);
    const json = await response.json();

    images = json.images;
  } else {
    images = [];
  }

  // Invalidate the current page content
  page_elements.forEach((el) => el.remove());
  page_elements = [];

  handle_scroll();
}

function populate_page(page_div, images) {
  if (page_div.childElementCount !== 0) {
    // The page is already populated
    return;
  }

  for (let img_sim of images) {
    let idx = img_sim[0];

    let img = document.createElement("img");
    img.src = `/img/${idx}.jpg`;

    let a = document.createElement("a");
    a.href = `/browse_similar/#${idx}`;
    a.appendChild(img);

    let tile = document.createElement("div");
    tile.className = "tile";
    tile.appendChild(a);

    page_div.appendChild(tile);
  }
}

function handle_scroll(_ev) {
  let upper_page = Math.floor(window.scrollY / window.innerHeight);
  let lower_page = upper_page + 1;

  let num_pages = Math.floor((images.length + 5) / 6);

  while (page_elements.length > num_pages) {
    page_elements.pop().remove();
  }

  let pages_elem = document.getElementById("pages");

  while (page_elements.length < num_pages) {
    let div = document.createElement("div");
    div.className = "page";

    pages_elem.appendChild(div);
    page_elements.push(div);
  }

  for (let page = 0; page < page_elements.length; page++) {
    // Clear all pages that are not currently on screen
    if (page != upper_page && page != lower_page) {
      page_elements[page].replaceChildren();
    }
  }

  let images_upper = images.slice(upper_page * 6, (upper_page + 1) * 6);
  let images_lower = images.slice(lower_page * 6, (lower_page + 1) * 6);

  if (images_upper.length > 0) {
    populate_page(page_elements[upper_page], images_upper);
  }

  if (images_lower.length > 0) {
    populate_page(page_elements[lower_page], images_lower);
  }
}

async function init() {
  console.log("OK let's go!");

  // Change the active tag based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    const filter = hash.substring(1);

    load_image_list(filter);
  });

  // Load and unload images based on scroll position
  window.addEventListener("scroll", handle_scroll);

  if (window.location.hash) {
    const hash = window.location.hash;
    const filter = hash.substring(1);

    load_image_list(filter);
    populate_filter_elem();
  }

  load_tag_list();
}
