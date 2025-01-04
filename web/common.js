"use strict";

export async function get_json(url) {
  const response = await fetch(url);
  const result = await response.json();

  return result;
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
