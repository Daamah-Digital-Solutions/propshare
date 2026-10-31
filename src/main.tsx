import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { startLanguage } from "./lib/i18n/language";

// Arabic / French: the dictionary is on before the first render (no flash of English)
void startLanguage().finally(() => {
  createRoot(document.getElementById("root")!).render(<App />);
});
