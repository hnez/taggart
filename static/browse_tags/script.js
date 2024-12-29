var page = null;
var images = null;
var page_elements = [];

async function load_image_list(tag_name) {
  const response = await fetch(`/tag/${tag_name}/images/by_embedding.json`);
  const json = await response.json();

  page = null;
  images = json.images;

  handle_scroll();
}

function populate_page(page_div, images) {
  if (page_div.childElementCount !== 0) {
    // The page is already populated
    return;
  }

  for (img_sim of images) {
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

  while (page_elements.length < num_pages) {
    let div = document.createElement("div");
    div.className = "page";

    document.body.appendChild(div);
    page_elements.push(div);
  }

  for (let page = 0; page < page_elements.length; page++) {
    // Clear all pages that are not currently on screen
    if (page != upper_page && page != lower_page) {
      page_elements[page].replaceChildren();
    }
  }

  images_upper = images.slice(upper_page * 6, (upper_page + 1) * 6);
  images_lower = images.slice(lower_page * 6, (lower_page + 1) * 6);

  populate_page(page_elements[upper_page], images_upper);
  populate_page(page_elements[lower_page], images_lower);
}

async function init() {
  console.log("OK let's go!");

  // Change the active tag based on the current URL hash value
  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    const tag_name = hash.substring(1);

    load_image_list(tag_name);
  });

  // Load and unload images based on scroll position
  window.addEventListener("scroll", handle_scroll);

  if (window.location.hash) {
    const hash = window.location.hash;
    const tag_name = hash.substring(1);

    load_image_list(tag_name);
  }
}
