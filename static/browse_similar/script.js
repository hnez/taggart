var pic = null;

function tag_span(image_id, tag_name, action) {
  let span = document.createElement("span");
  span.innerText = tag_name;
  span.className = "tag";

  if (action === "add") {
    span.onclick = (ev) => add_tag_to_image(image_id, tag_name, ev.target);
  } else {
    span.onclick = (ev) => remove_tag_from_image(image_id, tag_name, ev.target);
  }

  return span;
}

async function remove_tag_from_image(image_id, tag_name, span_elem) {
  // TODO: handle response
  await fetch(`/img/${image_id}/tags/current/${tag_name}`, {
    method: "DELETE",
  });

  document
    .getElementById("tags-suggested")
    .appendChild(tag_span(pic.id, tag_name, "add"));

  if (span_elem !== null) {
    span_elem.remove();
  }
}

async function add_tag_to_image(image_id, tag_name, span_elem) {
  // TODO: handle response
  await fetch(`/img/${image_id}/tags/current/${tag_name}`, { method: "PUT" });

  document
    .getElementById("tags-added")
    .appendChild(tag_span(pic.id, tag_name, "remove"));

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

  for (let tag_name of pic.tags.current) {
    tags_added_div.appendChild(tag_span(pic.id, tag_name, "remove"));
  }

  // Tags that other images have
  let tags_suggested_div = document.getElementById("tags-suggested");
  tags_suggested_div.querySelectorAll(".tag").forEach((tag) => tag.remove());

  for (let tag_name_and_similarity of pic.tags.available.reverse()) {
    let tag_name = tag_name_and_similarity[0];
    tags_suggested_div.appendChild(tag_span(pic.id, tag_name, "add"));
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
      add_tag_to_image(pic.id, ev.target.value, null);
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
