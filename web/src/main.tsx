import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Desktop from "./Desktop";
import "./styles.css";
import "./desktop.css";

createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("desktop") ? <Desktop /> : <App />);
