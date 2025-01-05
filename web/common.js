"use strict";

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
