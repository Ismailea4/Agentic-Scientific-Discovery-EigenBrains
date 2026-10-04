import { createFileRoute } from "@tanstack/react-router";

const ALLOWED = new Set(["sources", "state", "activity", "experiment", "stream"]);

/** Read-only relay to a user-supplied discovery-lab feed address, so the
 * browser can reach a feed that sends no CORS headers. GET only, and only the
 * feed's five documented paths. */
export const Route = createFileRoute("/lab-proxy/$")({
  server: {
    handlers: {
      GET: async ({ request, params }) => {
        const path = params._splat ?? "";
        if (!ALLOWED.has(path)) return new Response("Unknown lab path", { status: 404 });
        const url = new URL(request.url);
        const target = url.searchParams.get("target") ?? "";
        let base: URL;
        try {
          base = new URL(target);
        } catch {
          return new Response("Invalid lab address", { status: 400 });
        }
        if (base.protocol !== "https:" && base.protocol !== "http:") {
          return new Response("Invalid lab address", { status: 400 });
        }
        url.searchParams.delete("target");
        const upstream = new URL(`${base.pathname.replace(/\/$/, "")}/lab/${path}`, base.origin);
        upstream.search = url.searchParams.toString();
        try {
          const res = await fetch(upstream, {
            headers: { accept: request.headers.get("accept") ?? "*/*" },
            signal: request.signal,
          });
          return new Response(res.body, {
            status: res.status,
            headers: {
              "content-type": res.headers.get("content-type") ?? "application/json",
              "cache-control": "no-store",
            },
          });
        } catch (error) {
          return Response.json(
            { error: { code: "lab_unreachable", message: `Could not reach the lab at ${base.origin}`, details: {} } },
            { status: 502 },
          );
        }
      },
    },
  },
});
