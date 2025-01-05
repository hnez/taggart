"use strict";

function is_cropped(info, img) {
  return (
    info.crop.left !== 0 ||
    info.crop.top !== 0 ||
    (info.crop.width !== null && info.crop.width !== img.naturalWidth) ||
    (info.crop.height !== null && info.crop.height !== img.naturalHeight)
  );
}

function cropped_image_onload(ev, info) {
  const img = ev.target;

  if (!is_cropped(info, img)) return;

  const inner = img.parentNode;
  const outer = inner.parentNode;

  const outer_bb = outer.getBoundingClientRect();

  const scaling_factor = Math.min(
    outer_bb.width / info.crop.width,
    outer_bb.height / info.crop.height,
  );

  const crop_width = info.crop.width * scaling_factor;
  const crop_height = info.crop.height * scaling_factor;

  inner.style.position = "relative";
  inner.style.left = "50%";
  inner.style.top = "50%";
  inner.style.transform = "translate(-50%, -50%)";
  inner.style.width = `${crop_width}px`;
  inner.style.height = `${crop_height}px`;

  const left = info.crop.left * scaling_factor;
  const top = info.crop.top * scaling_factor;
  const img_width = img.naturalWidth * scaling_factor;
  const img_height = img.naturalHeight * scaling_factor;

  img.style.position = "absolute";
  img.style.left = `${-left}px`;
  img.style.top = `${-top}px`;
  img.style.width = `${img_width}px`;
  img.style.height = `${img_height}px`;
}

function crop_box_onmouseup(ev, outer, crop_box) {
  const ou_bb = outer.getBoundingClientRect();
  const cb_bb = crop_box.getBoundingClientRect();

  let left = cb_bb.left - ou_bb.left;
  let right = ou_bb.right - cb_bb.right;

  const off_left = ev.clientX - ou_bb.left;
  const off_right = ou_bb.right - ev.clientX;

  if (left === 0) {
    left = off_left;
  } else if (right === 0) {
    right = off_right;
  } else if (Math.abs(off_left - left) < Math.abs(off_right - right)) {
    left = off_left;
  } else {
    right = off_right;
  }

  let bottom = ou_bb.bottom - cb_bb.bottom;
  let top = cb_bb.top - ou_bb.top;

  const off_top = ev.clientY - ou_bb.top;
  const off_bottom = ou_bb.bottom - ev.clientY;

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

async function crop_button_onmouseup(ev, image_id, img, crop_box) {
  ev.stopPropagation();

  const img_bb = img.getBoundingClientRect();

  const scaling_factor_x = img.naturalWidth / img_bb.width;
  const scaling_factor_y = img.naturalHeight / img_bb.height;

  const scaling_factor = Math.max(scaling_factor_x, scaling_factor_y);

  const offset_x = (img_bb.width / 2) * (scaling_factor_x - scaling_factor);
  const offset_y = (img_bb.height / 2) * (scaling_factor_y - scaling_factor);

  const crop_box_bb = crop_box.getBoundingClientRect();

  const crop = {
    height: crop_box_bb.height * scaling_factor,
    left: (crop_box_bb.left - img_bb.left) * scaling_factor + offset_x,
    top: (crop_box_bb.top - img_bb.top) * scaling_factor + offset_y,
    width: crop_box_bb.width * scaling_factor,
  };

  const image_url = await post_json(`/images/${image_id}/crops`, crop);
  const new_id = image_url.match("images/([0-9]+)")[1];
  document.location = `#${new_id}`;
}

export function cropped_image(info, editor) {
  const img = document.createElement("img");
  img.loading = "lazy";
  img.style.objectFit = "contain";
  img.style.width = "100%";
  img.style.height = "100%";
  img.src = info.url;

  const inner = document.createElement("div");
  inner.style.overflow = "hidden";
  inner.append(img);

  const outer = document.createElement("div");
  outer.style.overflow = "hidden";
  outer.style.width = "100%";
  outer.style.height = "100%";
  outer.append(inner);

  if (editor) {
    const crop_button = document.createElement("button");
    crop_button.className = "crop-button";
    crop_button.textContent = "Add Crop";
    crop_button.addEventListener("mouseup", (ev) =>
      crop_button_onmouseup(ev, info.id, img, crop_box),
    );

    const crop_box = document.createElement("div");
    crop_box.className = "crop-box";
    crop_box.append(crop_button);

    outer.append(crop_box);
    outer.style.position = "relative";
    outer.addEventListener("mouseup", (ev) =>
      crop_box_onmouseup(ev, outer, crop_box),
    );
  }

  // TODO: add the original image width and height to `info`.
  // Then we can skip this alltogether if the images is not cropped.
  img.addEventListener("load", (ev) => cropped_image_onload(ev, info));

  return outer;
}

export async function get_json(url) {
  const response = await fetch(url);
  const result = await response.json();

  return result;
}

export async function post_json(url, content) {
  const body = JSON.stringify(content);

  const headers = new Headers();
  headers.append("Content-Type", "application/json");

  const response = await fetch(url, {
    body: body,
    headers: headers,
    method: "POST",
  });

  const created_url = response.headers.get("content-location");

  return created_url;
}

export async function put_json(url, content) {
  const body = JSON.stringify(content);

  const headers = new Headers();
  headers.append("Content-Type", "application/json");

  await fetch(url, {
    body: body,
    headers: headers,
    method: "PUT",
  });
}
