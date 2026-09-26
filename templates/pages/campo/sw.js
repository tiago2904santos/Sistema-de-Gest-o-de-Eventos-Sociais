/* m096 — Service worker do diário de bordo no celular (escopo /campo/diario/).
 *
 * Só guarda o necessário para a página abrir sem internet: a própria página do
 * link (rede primeiro, cópia guardada se não houver sinal) e os arquivos que ela
 * pede para guardar (CSS e JS). Os lançamentos não passam por aqui: ficam no
 * IndexedDB e a página os envia quando a conexão volta.
 */
"use strict";
const CACHE = "diario-campo-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith("diario-campo-") && n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// A página manda a lista do que guardar assim que o service worker fica pronto.
self.addEventListener("message", (evento) => {
  const dados = evento.data || {};
  if (dados.tipo !== "guardar" || !Array.isArray(dados.urls)) return;
  const urls = dados.urls.filter((u) => {
    try { return new URL(u, self.location.href).origin === self.location.origin; } catch (e) { return false; }
  });
  evento.waitUntil(
    caches.open(CACHE).then((cache) => Promise.all(urls.map((u) =>
      fetch(u, { credentials: "same-origin" }).then((r) => (r.ok ? cache.put(u, r) : null)).catch(() => null)
    )))
  );
});

self.addEventListener("fetch", (evento) => {
  const req = evento.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const escopo = new URL("./", self.registration.scope).pathname;

  if (req.mode === "navigate" && url.pathname.startsWith(escopo)) {
    // Rede primeiro: com sinal, a página vem com os dados atuais do servidor.
    evento.respondWith(
      fetch(req).then((resp) => {
        if (resp.ok) {
          const copia = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copia));
        }
        return resp;
      }).catch(() => caches.match(req, { ignoreSearch: true }).then((r) => r || new Response(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><p style='font-family:sans-serif;padding:16px'>Sem internet e esta página ainda não foi guardada no celular. Abra o link uma vez com internet.</p>",
        { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
      )))
    );
    return;
  }

  // Arquivos guardados (CSS/JS da página): o guardado na hora, e atualiza por trás.
  evento.respondWith(
    caches.open(CACHE).then((cache) => cache.match(req).then((guardado) => {
      const rede = fetch(req).then((resp) => {
        if (guardado && resp.ok) cache.put(req, resp.clone());
        return resp;
      });
      if (guardado) {
        rede.catch(() => null);
        return guardado;
      }
      return rede;
    }))
  );
});
