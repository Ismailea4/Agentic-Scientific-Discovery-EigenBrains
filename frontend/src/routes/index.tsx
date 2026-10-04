import { createFileRoute } from "@tanstack/react-router";
import App from "../noesis/App";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Noesis — Agentic Scientific Discovery" },
      { name: "description", content: "An inspectable Omnigent-orchestrated loop from scientific question to evidence, experiment, result, and updated decision." },
      { property: "og:title", content: "Noesis — Agentic Scientific Discovery" },
      { property: "og:description", content: "An inspectable Omnigent-orchestrated scientific discovery loop." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return <App />;
}
