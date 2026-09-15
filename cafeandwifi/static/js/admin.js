(function () {
  const LONDON = { lat: 51.5074, lng: -0.1278 };

  // ── Name mismatch note follows the Curator's typing ───────────────
  const nameInput = document.getElementById("name");
  const googleName = document.querySelector("[data-google-name]");
  if (nameInput && googleName) {
    const note = googleName.querySelector(".names-differ");
    const normalise = (text) => text.trim().replace(/\s+/g, " ").toLocaleLowerCase();
    nameInput.addEventListener("input", function () {
      const differ = normalise(nameInput.value) !== normalise(googleName.dataset.googleName);
      note.textContent = differ ? " — names differ — same business?" : "";
      note.classList.toggle("d-none", !differ);
    });
  }

  // ── Pin confirmation map ──────────────────────────────────────────
  const latitude = document.getElementById("latitude");
  const longitude = document.getElementById("longitude");

  function typedPosition() {
    const lat = parseFloat(latitude.value);
    const lng = parseFloat(longitude.value);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat: lat, lng: lng } : null;
  }

  function setInputs(latLng) {
    latitude.value = latLng.lat().toFixed(7);
    longitude.value = latLng.lng().toFixed(7);
  }

  const useGooglePin = document.querySelector("[data-use-google-pin]");
  if (useGooglePin) {
    useGooglePin.addEventListener("click", function () {
      const [lat, lng] = useGooglePin.closest("[data-google-pin]").dataset.googlePin.split(",");
      latitude.value = lat;
      longitude.value = lng;
      latitude.dispatchEvent(new Event("change"));
    });
  }

  // Called by the Google Maps loader once the API is ready.
  window.initPinMap = function () {
    const start = typedPosition();
    const map = new google.maps.Map(document.getElementById("pin-map"), {
      center: start || LONDON,
      zoom: start ? 18 : 11,
      clickableIcons: false,
      fullscreenControl: false,
      mapTypeControl: false,
      streetViewControl: false,
    });
    const marker = new google.maps.Marker({ map: start ? map : null, position: start, draggable: true });

    marker.addListener("dragend", (event) => setInputs(event.latLng));
    map.addListener("click", function (event) {
      marker.setPosition(event.latLng);
      marker.setMap(map);
      setInputs(event.latLng);
    });
    [latitude, longitude].forEach(function (input) {
      input.addEventListener("change", function () {
        const position = typedPosition();
        if (!position) return;
        marker.setPosition(position);
        marker.setMap(map);
        map.panTo(position);
      });
    });
  };
})();
