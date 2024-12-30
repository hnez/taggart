"use strict";

var pic = null;

function tag_span(image_id, tag_name, weight, where) {
  weight = Math.min(Math.max(weight, -1), 1);
  weight = (1 - weight) / 2;

  let hue = Math.floor(147 * (1 - weight));

  let span = document.createElement("span");
  span.innerText = tag_name;
  span.className = "tag";
  span.style.backgroundColor = `hsl(${hue}, 100%, 50%)`;

  if (where === "suggested") {
    span.onclick = (ev) =>
      set_tag_weight(image_id, tag_name, ev.shiftKey ? -1 : 1, ev.target);
  } else {
    span.onclick = (ev) => set_tag_weight(image_id, tag_name, 0, ev.target)
  }

  return span;
}

async function set_tag_weight(image_id, tag_name, weight, span_elem) {
  const content = { weight: weight };
  const body = JSON.stringify(content);

  const headers = new Headers();
  headers.append("Content-Type", "application/json");

  // TODO: handle response
  await fetch(`/img/${image_id}/tags/current/${tag_name}`, {
    method: "PUT",
    body: body,
    headers: headers,
  });

  if (weight === 0) {
    document
      .getElementById("tags-suggested")
      .appendChild(tag_span(pic.id, tag_name, 0, "suggested"));
  } else {
    document
      .getElementById("tags-added")
      .appendChild(tag_span(pic.id, tag_name, weight, "added"));
  }

  if (span_elem !== null) {
    span_elem.remove();
  }
}

function filter_suggested_tags(filter) {
  let tags_suggested_div = document.getElementById("tags-suggested");
  let tags = tags_suggested_div.querySelectorAll(".tag");

  for (let tag_span of tags) {
    let tag_name = tag_span.innerText;
    let hide = !tag_name.includes(filter);

    tag_span.classList.remove("hidden");

    if (hide) {
      tag_span.classList.add("hidden");
    }
  }
}

async function load_image(id) {
  // Download the image metadata
  const response = await fetch(`/img/${id}.json`);
  pic = await response.json();

  // Populate the main image
  document.getElementById("main").src = `/img/${pic.id}.jpg`;

  // Populate the roster of other images
  // Start with the next, previous, a shuffled next and shuffled previous
  // image.
  var roster = [
    pic.serial_prev,
    pic.serial_next,
    pic.shuffle_prev,
    pic.shuffle_next,
  ];

  // Then add images that the server deemed similar to this one.
  // From most to least similar (the server sends them in ascending order).

  for (let idx_sim of pic.similar.reverse()) {
    roster.push(idx_sim[0]);
  }

  var imgs = [];

  for (let idx of roster) {
    let img = document.createElement("img");
    img.className = "roster-element";
    img.src = `/img/${idx}.jpg`;

    let a = document.createElement("a");
    a.href = `#${idx}`;
    a.appendChild(img);

    imgs.push(a);
  }

  document.getElementById("roster").replaceChildren(...imgs);

  // Update the tag editor
  // Tags that are currently stored in the database for this image
  let tags_added_div = document.getElementById("tags-added");
  tags_added_div.querySelectorAll(".tag").forEach((tag) => tag.remove());

  for (let name_and_weight of pic.tags.current) {
    let name = name_and_weight[0];
    let weight = name_and_weight[1];
    tags_added_div.appendChild(tag_span(pic.id, name, weight, "added"));
  }

  // Tags that other images have
  let tags_suggested_div = document.getElementById("tags-suggested");
  tags_suggested_div.querySelectorAll(".tag").forEach((tag) => tag.remove());

  for (let tag_name_and_similarity of pic.tags.available.reverse()) {
    let tag_name = tag_name_and_similarity[0];
    let similarity = tag_name_and_similarity[1];

    if (pic.tags.current.find((nw) => nw[0] == tag_name) !== undefined) {
      continue
    }

    tags_suggested_div.appendChild(
      tag_span(pic.id, tag_name, similarity, "suggested"),
    );
  }

  // Apply the text filter on the suggested tags
  let tags_textbox = document.getElementById("tags-textbox");
  filter_suggested_tags(tags_textbox.value);
}

async function init() {
  console.log("OK let's go!");

  // Make the tag textbox interactive
  let tags_textbox = document.getElementById("tags-textbox");
  tags_textbox.addEventListener("input", (ev) =>
    filter_suggested_tags(ev.target.value),
  );
  tags_textbox.addEventListener("keyup", (ev) => {
    if (ev.key === "Enter") {
      let name = ev.target.value.trim();
      set_tag_weight(pic.id, name, 1, null);
      ev.target.value = "";
      filter_suggested_tags("");
    }
  });

  // Change the active image based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    const idx = Number(hash.substring(1));

    load_image(idx);
  });

  // Select the initial image based on the initial URL hash value
  let initial_image = 1;

  if (window.location.hash) {
    const hash = window.location.hash;
    initial_image = Number(hash.substring(1));
  }

  await load_image(initial_image);
}
