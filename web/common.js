"use strict";

export function cropped_image(info) {
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

  img.addEventListener("load", (_ev) => {
    const file_width = img.naturalWidth;
    const file_height = img.naturalHeight;

    if (info.crop.width === null) info.crop.width = file_width;
    if (info.crop.height === null) info.crop.height = file_height;

    // TODO: if file_width and file_height were part of the info we could
    // skip the onload alltogether.

    if (
      info.crop.left === 0 &&
      info.crop.top === 0 &&
      info.crop.width === file_width &&
      info.crop.height === file_height
    ) {
      return;
    }

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
    const img_width = file_width * scaling_factor;
    const img_height = file_height * scaling_factor;

    img.style.position = "absolute";
    img.style.left = `${-left}px`;
    img.style.top = `${-top}px`;
    img.style.width = `${img_width}px`;
    img.style.height = `${img_height}px`;
  });

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
