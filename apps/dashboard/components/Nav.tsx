"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Console" },
  { href: "/observatory", label: "Observatory" },
  { href: "/wind", label: "Wind" },
  { href: "/ward", label: "Ward" },
  { href: "/memory", label: "Memory" },
  { href: "/swarm", label: "Swarm" },
  { href: "/quarantine", label: "Quarantine" },
  { href: "/bronze", label: "Bronze" },
  { href: "/vm", label: "VM Lab" },
  { href: "/audit", label: "Audit" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="nav">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
