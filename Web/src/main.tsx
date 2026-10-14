import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";
// SDK lifecycles are deliberately not double-mounted by React StrictMode.
createRoot(document.getElementById("root")!).render(<App />);
