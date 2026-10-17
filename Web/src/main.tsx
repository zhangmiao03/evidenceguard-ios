import { createRoot } from "react-dom/client";
// SDK lifecycles are deliberately not double-mounted by React StrictMode.
async function boot() {
  const root = createRoot(document.getElementById("root")!);
  if (/^\/dashboard(?:\/index\.html|\/)?$/.test(location.pathname)) {
    const { default: Dashboard } = await import("./dashboard/Dashboard");
    document.body.style.margin = "0";
    document.title = "EvidenceGuard · 作品与 Agent 运行";
    root.render(<Dashboard />);
  } else {
    await Promise.all([import("./style.css"), import("./product.css")]);
    const { default: App } = await import("./App");
    root.render(<App />);
  }
}
void boot();
