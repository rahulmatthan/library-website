/* ============================================================
   The Living Bookshelf — render + interaction
   ============================================================ */
(function () {
  "use strict";

  // Cloth-bound colours, one per subgenre. Deep but muted so they read as
  // book cloth against the wood, with a cream foil title.
  var PALETTE = {
    science:         "#2f6f6b",
    technology:      "#34506e",
    history:         "#7c3a2c",
    biography:       "#8a6a34",
    politics:        "#5b3a55",
    "law-policy":    "#3b476b",
    economics:       "#4d6a37",
    society:         "#6b452c",
    self_help:       "#a8742e",
    arts:            "#8a3b54",
    food:            "#9c5530",
    fiction:         "#43607c",
    "science-fiction":"#37564f",
    "other-fiction": "#4a4a5c"
  };
  var FALLBACK_COLOR = "#4a5462";

  var REGION_LABEL = { india: "India", world: "World" };

  var state = {
    data: null,
    booksById: {},
    q: "",
    genre: "all",
    region: "all",
    sort: "shelf"
  };

  var els = {};

  // deterministic pseudo-random from a string so spine sizes are stable
  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967295;
  }

  function spineDims(b) {
    var r1 = hash(b.id);
    var r2 = hash(b.id + "h");
    var len = b.title.length;
    // bigger type for short titles; smaller for long ones (which may wrap)
    var fs = len <= 16 ? 15 : len <= 26 ? 13.5 : 12;
    // width: a touch thicker for longer titles; give long titles room for a 2nd column
    var w = Math.round(28 + Math.min(len, 30) * 0.3 + r1 * 9);
    if (len > 26) w = Math.max(w, 37);
    w = Math.min(w, 52);
    // height sized so the full title mostly fits one column at its font size
    var h = Math.round(34 + len * fs * 0.52 + r2 * 16);
    h = Math.max(182, Math.min(h, 236));
    return { w: w, h: h, fs: fs };
  }

  // Spine colour: sampled from the book's own cover, so the shelf is
  // multi-coloured like a real one. Fall back to the subgenre cloth colour.
  function color(b) { return b.spineColor || PALETTE[b.subgenre] || FALLBACK_COLOR; }

  function luminance(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return 0;
    var r = parseInt(m[1], 16), g = parseInt(m[2], 16), b = parseInt(m[3], 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  }

  function authorText(b) {
    if (!b.authors || !b.authors.length) return "";
    if (b.authors.length === 1) return b.authors[0];
    if (b.authors.length === 2) return b.authors[0] + " & " + b.authors[1];
    return b.authors[0] + " et al.";
  }

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  // ---------------------------------------------------------- render
  var GAP = 3;        // px between spines
  var ROW_PAD = 26;   // px of horizontal padding inside a shelf row
  var BOOKEND_W = 46; // px footprint of a sub-genre bookend (plate + foot + margins)

  function shelfWidth() {
    var w = els.library ? els.library.clientWidth : 0;
    return Math.max(300, (w || 1200) - 44);   // minus .library padding
  }

  function subName(label) {
    var parts = label.split(" · ");
    return parts.length === 2 ? parts[1] : label;
  }

  // Greedy-pack a mixed sequence of {book} and {bookend} items into fixed-width
  // rows; overflow starts a new shelf below. A bookend never ends a row (it
  // introduces the next sub-genre, so it moves down with its books).
  function packItems(items, maxW) {
    var rows = [], cur = [], curW = 0;
    var limit = maxW - ROW_PAD;
    items.forEach(function (it) {
      var w = it.type === "label" ? 0
        : (it.type === "gap" ? CAT_GAP : spineDims(it.b).w) + GAP;
      if (cur.length && curW + w > limit) { rows.push(cur); cur = []; curW = 0; }
      cur.push(it); curW += w;
    });
    if (cur.length) rows.push(cur);
    // a trailing gap/label must not dangle at a row's end — move it down with
    // its category's books
    for (var i = 0; i < rows.length - 1; i++) {
      while (rows[i].length && /^(gap|label)$/.test(rows[i][rows[i].length - 1].type)) {
        rows[i + 1].unshift(rows[i].pop());
      }
    }
    // a category that wraps to a new row needs no leading gap (the break separates)
    rows.forEach(function (r) { while (r.length && r[0].type === "gap") r.shift(); });
    return rows.filter(function (r) { return r.length; });
  }

  function render() {
    var lib = els.library;
    lib.innerHTML = "";
    var W = shelfWidth();
    state.data.rooms.forEach(function (room) {
      var section = el("section", "room");
      section.id = "room-" + room.id;

      var head = el("div", "room-head");
      head.appendChild(el("h2", null, room.zone === "Fiction" ? "Fiction" : room.zone));
      head.appendChild(el("span", "zone-sub",
        room.genre === "fiction" ? "Stories & speculation" : "Non-fiction"));
      head.appendChild(el("div", "room-rule"));
      section.appendChild(head);

      // one continuous run of books for the whole room, sub-genres separated by
      // a bookend divider (which carries the sub-genre name)
      var items = [];
      room.shelves.forEach(function (shelf, idx) {
        if (idx > 0) items.push({ type: "gap" });   // one-book space before a new category
        items.push({ type: "label", label: subName(shelf.label) });
        sortBooks(shelf.bookIds.map(function (id) { return state.booksById[id]; })
          .filter(Boolean))
          .forEach(function (b) { items.push({ type: "book", b: b }); });
      });

      packItems(items, W).forEach(function (rowItems) {
        var row = el("div", "shelf-row");
        rowItems.forEach(function (it) {
          row.appendChild(it.type === "book" ? spineEl(it.b)
            : it.type === "gap" ? gapEl() : labelEl(it.label));
        });
        section.appendChild(row);
        section.appendChild(el("div", "shelf-plank"));
      });
      lib.appendChild(section);
    });
    apply();
  }

  var CAT_GAP = 42;  // one-book-wide space between categories

  function gapEl() { return el("div", "shelf-gap"); }

  // zero-width marker: the category's books start directly above it, and its
  // brass nameplate overflows to the right onto the shelf beneath them
  function labelEl(label) {
    var d = el("div", "shelf-tag");
    d.appendChild(el("span", null, label));
    return d;
  }

  function spineEl(b) {
    var dims = spineDims(b);
    var btn = el("button", "spine");
    btn.style.setProperty("--w", dims.w + "px");
    btn.style.setProperty("--h", dims.h + "px");
    btn.style.setProperty("--fs", dims.fs + "px");
    btn.style.setProperty("--c", color(b));
    if (dims.w < 34) btn.classList.add("thin");
    btn.dataset.id = b.id;
    btn.setAttribute("aria-label", b.title + (b.authors.length ? ", " + authorText(b) : ""));

    if (b.coverThumb || b.cover) {
      // The spine wears an abstracted wash of its own cover, so opening the
      // book feels continuous with the spine.
      btn.classList.add("has-art");
      var art = el("div", "spine-art");
      art.style.backgroundImage = "url('" + (b.coverThumb || b.cover).replace(/'/g, "%27") + "')";
      btn.appendChild(art);
    } else if (luminance(color(b)) > 0.6) {
      btn.classList.add("light-spine");
    }

    btn.appendChild(el("span", "spine-title", b.title));
    var foot = authorText(b).split(" ").pop();
    if (foot) btn.appendChild(el("span", "spine-foot", foot));

    btn.addEventListener("click", function () { openDrawer(b); });
    b._spine = btn;
    return btn;
  }

  // ---------------------------------------------------------- filter + sort
  function matches(b) {
    if (state.genre !== "all" && b.genre !== state.genre) return false;
    if (state.region !== "all" && b.region !== state.region) return false;
    if (state.q) {
      var hay = (b.title + " " + b.authors.join(" ")).toLowerCase();
      if (hay.indexOf(state.q) === -1) return false;
    }
    return true;
  }

  function authorKey(b) {
    if (!b.authors || !b.authors.length) return "zzzz";
    var parts = b.authors[0].trim().split(/\s+/);
    return (parts[parts.length - 1] || b.authors[0]).toLowerCase();
  }

  function sortBooks(books) {
    var arr = books.slice();
    if (state.sort === "title") {
      arr.sort(function (a, b) { return a.title.localeCompare(b.title); });
    } else if (state.sort === "author") {
      arr.sort(function (a, b) {
        return authorKey(a).localeCompare(authorKey(b)) || a.title.localeCompare(b.title);
      });
    } else if (state.sort === "recent") {
      arr.sort(function (a, b) {
        return (b.completed || "0").localeCompare(a.completed || "0");
      });
    }
    return arr; // "shelf" keeps precomputed walk order
  }

  function apply() {
    var visibleTotal = 0;
    var filtering = state.q || state.genre !== "all" || state.region !== "all";
    els.library.querySelectorAll(".room").forEach(function (roomEl) {
      var roomVisible = 0;
      roomEl.querySelectorAll(".spine").forEach(function (sp) {
        var ok = matches(state.booksById[sp.dataset.id]);
        sp.classList.toggle("dim", !ok);
        if (ok) roomVisible++;
      });
      // while filtering, hide section labels so results aren't cluttered
      roomEl.querySelectorAll(".shelf-tag").forEach(function (be) {
        be.style.visibility = filtering ? "hidden" : "";
      });
      roomEl.style.display = roomVisible ? "" : "none";
      visibleTotal += roomVisible;
    });
    els.empty.classList.toggle("show", visibleTotal === 0);
    els.empty.hidden = visibleTotal !== 0;
  }

  // ---------------------------------------------------------- drawer
  function openDrawer(b) {
    var body = els.drawerBody;
    body.innerHTML = "";

    var hero = el("div", "d-hero");
    if (b.cover) {
      var img = el("img", "d-cover");
      img.src = b.cover; img.alt = "Cover of " + b.title; img.loading = "lazy";
      img.onerror = function () {
        if (b.coverRemote && img.src !== b.coverRemote) { img.src = b.coverRemote; return; }
        img.replaceWith(placeholderCover(b));
      };
      hero.appendChild(img);
    } else {
      hero.appendChild(placeholderCover(b));
    }

    var meta = el("div", "d-meta");
    meta.appendChild(el("h3", "d-title", b.title));
    if (b.authors.length) meta.appendChild(el("p", "d-author", authorText(b)));
    var tags = el("div", "d-tags");
    tags.appendChild(el("span", "d-tag genre", b.genre === "fiction" ? "Fiction" : "Non-fiction"));
    if (b.subgenreLabel && b.subgenreLabel.toLowerCase() !== b.genre)
      tags.appendChild(el("span", "d-tag", b.subgenreLabel));
    if (b.region && REGION_LABEL[b.region]) tags.appendChild(el("span", "d-tag", REGION_LABEL[b.region]));
    meta.appendChild(tags);
    hero.appendChild(meta);
    body.appendChild(hero);

    var sum = el("div", "d-summary");
    if (b.summary) { sum.textContent = b.summary; }
    else { sum.className = "d-summary empty"; sum.textContent = "A note on this one is on its way."; }
    body.appendChild(sum);

    var foot = el("div", "d-foot");
    var bits = [];
    if (b.completed) bits.push("Read " + prettyDate(b.completed));
    foot.textContent = bits.join(" · ");
    if (bits.length) body.appendChild(foot);

    els.drawer.classList.add("open");
    els.drawer.setAttribute("aria-hidden", "false");
    els.scrim.hidden = false;
    requestAnimationFrame(function () { els.scrim.classList.add("show"); });
    els.drawerClose.focus();
  }

  function placeholderCover(b) {
    var d = el("div", "d-cover placeholder");
    d.style.background = "linear-gradient(150deg," + color(b) + ", rgba(0,0,0,.35))";
    d.style.color = "#f3e9d6";
    d.appendChild(el("span", null, b.title));
    return d;
  }

  function prettyDate(s) {
    var d = new Date(s + "T00:00:00");
    if (isNaN(d)) return s;
    return d.toLocaleDateString("en-IN", { year: "numeric", month: "short" });
  }

  function closeDrawer() {
    els.drawer.classList.remove("open");
    els.drawer.setAttribute("aria-hidden", "true");
    els.scrim.classList.remove("show");
    setTimeout(function () { els.scrim.hidden = true; }, 260);
  }

  // ---------------------------------------------------------- controls
  function buildControls() {
    var f = els.filters;
    f.innerHTML = "";

    var genres = {};
    state.data.books.forEach(function (b) { if (b.genre) genres[b.genre] = 1; });
    if (Object.keys(genres).length > 1) {
      group(f, "genre", [
        ["all", "All"], ["non-fiction", "Non-fiction"], ["fiction", "Fiction"]
      ]);
    }

    var regions = {};
    state.data.books.forEach(function (b) { if (b.region) regions[b.region] = 1; });
    if (Object.keys(regions).length > 1) {
      group(f, "region", [["all", "Everywhere"]].concat(
        Object.keys(regions).sort().map(function (r) { return [r, REGION_LABEL[r] || r]; })));
    }

    var sortWrap = el("div", "filters");
    sortWrap.style.marginLeft = "6px";
    [["shelf", "Shelf order"], ["author", "By author"], ["recent", "Recent"], ["title", "Title A–Z"]]
      .forEach(function (opt) {
        var c = el("button", "chip sort", opt[1]);
        c.setAttribute("aria-pressed", state.sort === opt[0]);
        c.addEventListener("click", function () {
          if (state.sort === opt[0]) return;
          state.sort = opt[0];
          sortWrap.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
          c.setAttribute("aria-pressed", "true");
          render();   // re-sort + re-pack the shelves
        });
        sortWrap.appendChild(c);
      });
    f.appendChild(sortWrap);
  }

  function group(container, key, opts) {
    opts.forEach(function (opt) {
      var c = el("button", "chip", opt[1]);
      c.setAttribute("aria-pressed", state[key] === opt[0]);
      c.dataset.group = key;
      c.addEventListener("click", function () {
        state[key] = opt[0];
        container.querySelectorAll('.chip[data-group="' + key + '"]').forEach(function (x) {
          x.setAttribute("aria-pressed", "false");
        });
        c.setAttribute("aria-pressed", "true");
        apply();
      });
      container.appendChild(c);
    });
  }

  function buildRoomNav() {
    var nav = els.roomnav;
    nav.innerHTML = "";
    state.data.rooms.forEach(function (room) {
      var a = el("a", null, room.zone === "Fiction" ? "Fiction" : room.zone);
      a.href = "#room-" + room.id;
      nav.appendChild(a);
    });
  }

  // ---------------------------------------------------------- init
  function init(data) {
    state.data = data;
    data.books.forEach(function (b) { state.booksById[b.id] = b; });

    els = {
      library: document.getElementById("library"),
      filters: document.getElementById("filters"),
      roomnav: document.getElementById("roomnav"),
      search: document.getElementById("search"),
      empty: document.getElementById("empty"),
      drawer: document.getElementById("drawer"),
      drawerBody: document.getElementById("drawerBody"),
      drawerClose: document.getElementById("drawerClose"),
      scrim: document.getElementById("scrim")
    };
    document.getElementById("footcount").textContent = data.count + " books";

    buildControls();
    buildRoomNav();
    render();

    var t;
    els.search.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () {
        state.q = els.search.value.trim().toLowerCase();
        apply();
      }, 90);
    });
    els.drawerClose.addEventListener("click", closeDrawer);
    els.scrim.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });

    // Re-pack shelves to the new width when the window resizes.
    var rt, lastW = shelfWidth();
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (Math.abs(shelfWidth() - lastW) < 24) return;  // ignore tiny changes
        lastW = shelfWidth();
        render();
      }, 200);
    });
  }

  fetch(window.LIBRARY_URL)
    .then(function (r) { return r.json(); })
    .then(init)
    .catch(function (err) {
      document.getElementById("loading").textContent =
        "Couldn't load the library. " + err;
    });
})();
