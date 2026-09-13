/* Service worker: the shell is cache-first so the app opens instantly and
   works with no signal; the recipe data is network-first so a fresh clip
   shows up as soon as you're online, without waiting for a new worker.

   VERSION is rewritten by tools/build.py from a hash of the shell files, so
   deploying changed CSS or JS retires the old cache on its own. */

const VERSION = "0cf6ce9bf84c";
const SHELL = `shell-${VERSION}`;
const DATA = "data-v1";

const SHELL_FILES = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "assets/style.css",
  "assets/app.js",
  "assets/fonts.css",
  "assets/icons.svg",
  "assets/favicon.svg",
  "assets/icon-192.png",
  "assets/fonts/barlow-400.woff2",
  "assets/fonts/barlow-500.woff2",
  "assets/fonts/barlow-600.woff2",
  "assets/fonts/barlow-condensed-600.woff2",
  "assets/fonts/barlow-condensed-700.woff2",
  "assets/fonts/dm-mono-400.woff2",
  "assets/fonts/dm-mono-500.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.endsWith("/data/recipes.json")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(DATA).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || Response.error()))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).catch(() => {
      // A deep link like #/r/x is still index.html; serve the shell offline.
      if (request.mode === "navigate") return caches.match("index.html");
      return Response.error();
    }))
  );
});
