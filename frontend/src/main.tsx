import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { createHashRouter, Navigate, RouterProvider } from "react-router-dom";
import "./index.css";
import { store } from "@/AuthStore/store";
import ProtectedRoute from "@/guard/protectedRoutes";
import PublicRoute from "@/guard/publicRoutes";
import { Layout } from "@/components/Layout";
import { Login } from "@/pages/Login";
import { Home } from "@/pages/Home";
import { Analyse } from "@/pages/Analyse";
import { LiveLink } from "@/pages/LiveLink";
import { Provenance } from "@/pages/Provenance";
import { Results } from "@/pages/Results";
import { Attacks } from "@/pages/Attacks";
import { AttackLab } from "@/pages/AttackLab";
import { Station } from "@/pages/Station";
import { AuditLog } from "@/pages/AuditLog";
import { About } from "@/pages/About";

// Hash routing so deep links work from a static file:// or any sub-path, offline.
// Signed-out visitors land on /login; signing in opens the dashboard at "/".
const router = createHashRouter([
  {
    element: <PublicRoute />,
    children: [{ path: "/login", element: <Login /> }],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: "/",
        element: <Layout />,
        children: [
          { index: true, element: <Home /> },
          { path: "dashboard", element: <Navigate to="/" replace /> },
          { path: "analyse", element: <Analyse /> },
          { path: "live", element: <LiveLink /> },
          { path: "provenance", element: <Provenance /> },
          { path: "results", element: <Results /> },
          { path: "attacks", element: <Attacks /> },
          { path: "lab", element: <AttackLab /> },
          { path: "station", element: <Station /> },
          { path: "audit", element: <AuditLog /> },
          { path: "about", element: <About /> },
          { path: "*", element: <Home /> },
        ],
      },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Provider store={store}>
      <RouterProvider router={router} />
    </Provider>
  </React.StrictMode>,
);
