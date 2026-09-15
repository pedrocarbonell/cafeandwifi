(function () {
  const LONDON = { lat: 51.5074, lng: -0.1278 };
  const DESKTOP = window.matchMedia("(min-width: 992px)");

  const page = document.querySelector(".map-page");
  const form = document.getElementById("filter-form");
  const price = document.getElementById("max-price");
  const priceValue = form.querySelector("[data-price-value]");
  const activeCount = document.querySelector("[data-active-filter-count]");
  const matchCount = form.querySelector("[data-match-count]");
  const noMatch = document.querySelector("[data-no-match]");
  const mapInset = document.querySelector(".map-inset");
  const sheetEl = document.getElementById("cafe-sheet");
  const sheetBody = sheetEl.querySelector("[data-cafe-sheet-body]");

  let map = null;
  let infoWindow = null;
  let markers = [];
  let cafes = [];
  let openCafeId = null;
  let sharedCafe = page.dataset.sharedCafe ? JSON.parse(page.dataset.sharedCafe) : null;
  let requestNumber = 0;
  const photos = new Map(); // photo lookups for this page view only, never stored

  // ── Filters ───────────────────────────────────────────────────────
  function priceIsAny() {
    return price.value === price.max;
  }

  function showPrice() {
    priceValue.textContent = priceIsAny() ? "Any" : pounds(Number(price.value));
  }

  function showActiveCount() {
    let n = form.querySelectorAll(".filter-switch input:checked").length;
    if (form.elements.min_seating.value) n += 1;
    if (!priceIsAny()) n += 1;
    activeCount.textContent = n ? " · " + n : "";
  }

  function filterQuery() {
    const params = new URLSearchParams();
    form.querySelectorAll(".filter-switch input:checked").forEach(function (input) {
      params.set(input.name, "1");
    });
    if (form.elements.min_seating.value) params.set("min_seating", form.elements.min_seating.value);
    if (!priceIsAny()) params.set("max_price_pence", price.value);
    return params.toString();
  }

  async function loadCafes() {
    const thisRequest = ++requestNumber;
    const response = await fetch(page.dataset.cafesUrl + "?" + filterQuery());
    if (thisRequest !== requestNumber) return; // a newer filter change won
    if (!response.ok) {
      matchCount.textContent = "Could not load cafes. Reload to try again.";
      return;
    }
    const body = await response.json();
    cafes = body.cafes;
    if (sharedCafe) {
      matchCount.textContent = "1 cafe shown";
    } else {
      showMatches(body.count);
    }
    renderMarkers();
    if (openCafeId !== null && !cafes.some((cafe) => cafe.id === openCafeId)) closeCard();
  }

  function showMatches(count) {
    matchCount.innerHTML = "";
    const strong = document.createElement("strong");
    strong.textContent = count;
    matchCount.append(strong, count === 1 ? " cafe matches" : " cafes match");
    noMatch.classList.toggle("d-none", count !== 0);
    mapInset.classList.toggle("is-empty", count === 0);
  }

  let debounce = null;
  function onFilterChange() {
    showPrice();
    showActiveCount();
    leaveSharedView();
    clearTimeout(debounce);
    debounce = setTimeout(loadCafes, 120);
  }

  form.addEventListener("input", onFilterChange);
  form.addEventListener("change", onFilterChange);

  document.querySelectorAll("[data-clear-filters]").forEach(function (button) {
    button.addEventListener("click", function () {
      form.reset();
      onFilterChange();
    });
  });

  // ── Shared link landing ───────────────────────────────────────────
  function leaveSharedView() {
    if (!sharedCafe) return;
    sharedCafe = null;
    closeCard(); // it was opened without a Share button
    const strip = document.querySelector("[data-shared-strip]");
    if (strip) strip.remove();
    history.replaceState(null, "", "/");
  }

  const seeAll = document.querySelector("[data-see-all]");
  if (seeAll) {
    seeAll.addEventListener("click", function (event) {
      event.preventDefault();
      leaveSharedView();
      loadCafes();
    });
  }

  const dismissNote = document.querySelector("[data-dismiss-note]");
  if (dismissNote) {
    dismissNote.addEventListener("click", function () {
      dismissNote.closest("[data-missing-note]").remove();
      history.replaceState(null, "", "/");
    });
  }

  // ── Map and pins ──────────────────────────────────────────────────
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function pinIcon() {
    return {
      path: "M12 0C5.4 0 0 5.2 0 11.7 0 20.5 12 32 12 32s12-11.5 12-20.3C24 5.2 18.6 0 12 0zm0 16a4.3 4.3 0 1 1 0-8.6 4.3 4.3 0 0 1 0 8.6z",
      fillColor: cssVar("--color-accent"),
      fillOpacity: 1,
      strokeColor: cssVar("--color-accent-700"),
      strokeWeight: 1,
      scale: 1.1,
      anchor: new google.maps.Point(12, 32),
    };
  }

  function renderMarkers() {
    if (!map) return;
    markers.forEach((marker) => marker.setMap(null));
    const shown = sharedCafe ? [sharedCafe] : cafes;
    markers = shown.map(function (cafe) {
      const marker = new google.maps.Marker({
        map: map,
        position: { lat: cafe.latitude, lng: cafe.longitude },
        title: cafe.name,
        icon: pinIcon(),
      });
      marker.addListener("click", () => openCard(cafe, marker));
      return marker;
    });
  }

  // Called by the Google Maps loader once the API is ready.
  window.initCafeMap = function () {
    map = new google.maps.Map(document.getElementById("map"), {
      center: sharedCafe ? { lat: sharedCafe.latitude, lng: sharedCafe.longitude } : LONDON,
      zoom: sharedCafe ? 16 : 12,
      clickableIcons: false,
      fullscreenControl: false,
      mapTypeControl: false,
      streetViewControl: false,
      gestureHandling: "greedy",
    });
    infoWindow = new google.maps.InfoWindow({ headerDisabled: true, maxWidth: 360 });
    infoWindow.addListener("closeclick", () => (openCafeId = null));
    renderMarkers();
    if (sharedCafe) openCard(sharedCafe, markers[0]);
  };

  // ── Cafe card ─────────────────────────────────────────────────────
  function pounds(pence) {
    return "£" + (pence / 100).toFixed(2);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function drawIcons() {
    lucide.createIcons({ attrs: { "stroke-width": 2.75, width: 18, height: 18 } });
  }

  function icon(name) {
    const i = document.createElement("i");
    i.dataset.lucide = name;
    return i;
  }

  function attributeTile(iconName, label, on) {
    const tile = el("div", "attr " + (on === undefined ? "attr-value" : on ? "attr-on" : "attr-off"));
    tile.append(icon(iconName));
    if (on === undefined) {
      tile.append(el("strong", "", label.value), el("span", "", label.name));
    } else {
      tile.append(el("span", "", label));
    }
    return tile;
  }

  function navButton(href, className, glyph, app) {
    const link = el("a", "btn " + className + " nav-button");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener";
    const tile = el("span", "nav-logo");
    tile.append(icon(glyph));
    const text = el("span", "nav-text");
    text.append(el("small", "", "Open in"), el("span", "", app));
    link.append(tile, text);
    return link;
  }

  function buildCard(cafe, { canShare }) {
    const card = el("article", "cafe-card");
    card.dataset.cafeId = cafe.id;

    const close = el("button", "btn-close cafe-card-close");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.addEventListener("click", closeCard);

    const photo = el("div", "cafe-photo");
    const placeholder = el("div", "cafe-photo-placeholder");
    placeholder.append(icon("coffee"));
    photo.append(placeholder);

    const name = el("h2", "cafe-name", cafe.name);
    const neighbourhood = el("p", "cafe-neighbourhood", cafe.neighbourhood);

    const attrs = el("div", "attr-row");
    attrs.append(
      attributeTile("wifi", "Wi-Fi", cafe.has_wifi),
      attributeTile("plug", "Sockets", cafe.has_sockets),
      attributeTile("droplet", "Toilet", cafe.has_toilet),
      attributeTile(
        cafe.calls_permitted ? "phone" : "phone-off",
        cafe.calls_permitted ? "Calls" : "No calls",
        cafe.calls_permitted
      ),
      attributeTile("users", { value: cafe.seating_capacity, name: "Seating" }),
      attributeTile("pound-sterling", { value: pounds(cafe.coffee_price_pence), name: "Coffee" })
    );

    const actions = el("div", "cafe-actions");
    if (cafe.google_maps_url) {
      actions.append(navButton(cafe.google_maps_url, "btn-primary", "map-pin", "Google Maps"));
    }
    actions.append(navButton(cafe.waze_url, "btn-outline-secondary", "navigation", "Waze"));
    if (canShare) {
      const share = el("button", "btn btn-outline-secondary share-button");
      share.type = "button";
      share.setAttribute("aria-label", "Share " + cafe.name);
      share.append(icon("share-2"));
      share.addEventListener("click", () => shareCafe(cafe, share));
      actions.append(share);
    }

    const credit = el("p", "photo-credit");
    const body = el("div", "cafe-card-body");
    body.append(name, neighbourhood, attrs, actions, credit);
    card.append(close, photo, body);
    return card;
  }

  function openCard(cafe, marker) {
    openCafeId = cafe.id;
    const card = buildCard(cafe, { canShare: !sharedCafe });
    if (DESKTOP.matches && infoWindow && marker) {
      bootstrap.Offcanvas.getOrCreateInstance(sheetEl).hide();
      infoWindow.setContent(card);
      infoWindow.open({ map: map, anchor: marker });
    } else {
      if (infoWindow) infoWindow.close();
      sheetBody.replaceChildren(card);
      bootstrap.Offcanvas.getOrCreateInstance(sheetEl).show();
      if (map) map.panTo({ lat: cafe.latitude, lng: cafe.longitude });
    }
    drawIcons();
    loadPhoto(cafe, card);
  }

  function closeCard() {
    openCafeId = null;
    if (infoWindow) infoWindow.close();
    bootstrap.Offcanvas.getOrCreateInstance(sheetEl).hide();
  }

  sheetEl.addEventListener("hidden.bs.offcanvas", function () {
    if (!infoWindow || !infoWindow.isOpen) openCafeId = null;
  });

  // Google photos are fetched only when a card opens, to spare the free allowance.
  async function lookUpPhoto(placeId) {
    const { Place } = await google.maps.importLibrary("places");
    const place = new Place({ id: placeId });
    await place.fetchFields({ fields: ["photos"] });
    const photo = place.photos && place.photos[0];
    if (!photo) return null;
    const author = photo.authorAttributions && photo.authorAttributions[0];
    return {
      src: photo.getURI({ maxWidth: 720 }),
      author: author ? { name: author.displayName, uri: author.uri } : null,
    };
  }

  async function loadPhoto(cafe, card) {
    if (!cafe.google_place_id || !window.google) return;
    if (!photos.has(cafe.google_place_id)) {
      photos.set(cafe.google_place_id, lookUpPhoto(cafe.google_place_id).catch(() => null));
    }
    const photo = await photos.get(cafe.google_place_id);
    if (!photo || !card.isConnected) return;

    const img = el("img", "washed");
    img.alt = "Photo of " + cafe.name;
    img.src = photo.src;
    img.addEventListener("load", () => card.querySelector(".cafe-photo").replaceChildren(img));

    if (photo.author) {
      const credit = card.querySelector(".photo-credit");
      credit.append("Photo: ");
      if (photo.author.uri) {
        const link = el("a", "", photo.author.name);
        link.href = photo.author.uri;
        link.target = "_blank";
        link.rel = "noopener";
        credit.append(link);
      } else {
        credit.append(photo.author.name);
      }
    }
  }

  // ── Sharing ───────────────────────────────────────────────────────
  async function shareCafe(cafe, button) {
    const onPhone = window.matchMedia("(pointer: coarse)").matches;
    if (onPhone && navigator.share) {
      try {
        await navigator.share({ title: cafe.name, text: cafe.name + " · " + cafe.neighbourhood, url: cafe.share_url });
      } catch (error) {
        /* the Visitor closed the share sheet */
      }
      return;
    }
    const copied = await copyText(cafe.share_url);
    const label = button.getAttribute("aria-label");
    button.classList.add("copied");
    button.replaceChildren(icon(copied ? "check" : "x"), el("span", "", copied ? " Link copied" : " Copy failed"));
    drawIcons();
    setTimeout(function () {
      button.classList.remove("copied");
      button.replaceChildren(icon("share-2"));
      button.setAttribute("aria-label", label);
      drawIcons();
    }, 2000);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      // Clipboard API needs a secure context; fall back for plain http.
      const input = el("textarea");
      input.value = text;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.append(input);
      input.select();
      const ok = document.execCommand("copy");
      input.remove();
      return ok;
    }
  }

  showPrice();
  showActiveCount();
  loadCafes();
})();
