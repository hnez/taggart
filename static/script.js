var pic = null;

async function load_image(id) {
  const response = await fetch(`/img/${id}.json`);
  pic = await response.json();

  document.getElementById("main").src = `/img/${pic.id}.jpg`;

  var roster = [
    pic.serial_prev,
    pic.serial_next,
    pic.shuffle_prev,
    pic.shuffle_next,
  ];

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
}

async function init() {
  console.log("OK let's go!");

  window.addEventListener("hashchange", (ev) => {
    const url = URL.parse(ev.newURL);
    const hash = url.hash;
    const idx = Number(hash.substring(1));

    load_image(idx);
  });

  await load_image(1);
}
