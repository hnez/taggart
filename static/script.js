var config = {
  keys: {
    up: ["ArrowUp", "PageUp", "Backspace"],
    down: ["ArrowDown", "PageDown", " "],
    left: ["ArrowLeft"],
    right: ["ArrowRight"],
    fullscreen: ["f"],
  },
};

var undo = [];
var pic = null;

async function chpic(tpe, ud) {
  var picnum = pic !== null ? pic.id : 1;

  if (tpe === "s") {
    if (ud > 0) {
      picnum = pic.serial_next;
    } else {
      picnum = pic.serial_prev;
    }
  }

  if (tpe === "r") {
    if (ud > 0) {
      picnum = pic.shuffle_next;
    } else {
      picnum = pic.shuffle_prev;
    }
  }

  undo.push(picnum);

  const response = await fetch(`/img/${picnum}.json`);
  pic = await response.json();

  document.getElementById("icenter").src = `/img/${pic.id}.jpg`;
  document.getElementById("itop").src = `/img/${pic.serial_prev}.jpg`;
  document.getElementById("ibottom").src = `/img/${pic.serial_next}.jpg`;

  document.getElementById("ileft").src = `/img/${pic.shuffle_prev}.jpg`;
  document.getElementById("iright").src = `/img/${pic.shuffle_next}.jpg`;
}

function fscreen() {
  var haupt = document.getElementById("icenter");

  if (haupt.classList.contains("fullscreen")) {
    haupt.classList.remove("fullscreen");
  } else {
    haupt.classList.add("fullscreen");
  }
}

async function init() {
  console.log("OK let's go!");

  document.body.addEventListener(
    "keyup",
    (k) => {
      if (config.keys.up.includes(k.key)) chpic("s", -1);
      if (config.keys.down.includes(k.key)) chpic("s", 1);
      if (config.keys.left.includes(k.key)) chpic("r", -1);
      if (config.keys.right.includes(k.key)) chpic("r", 1);
      if (config.keys.fullscreen.includes(k.key)) fscreen();
    },
    false,
  );

  await chpic("init", 0);
}
