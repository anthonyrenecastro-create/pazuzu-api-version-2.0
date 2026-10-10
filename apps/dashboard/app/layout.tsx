import "./globals.css";
import Nav from "../components/Nav";

export const metadata = {
  title: "PAZUZU v2 — Intelligence Dashboard",
  description: "Operations console for PAZUZU-API v2.0: twelve stations, dual ward, memory ring, quarantine, bronze lab.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="brand">
            PAZUZU <span>v2.0 · INTELLIGENCE CONSOLE</span>
          </div>
          <div className="env">
            API&nbsp;{process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
          </div>
        </header>
        <Nav />
        <main className="main">{children}</main>
      </body>
    </html>
  );
}
