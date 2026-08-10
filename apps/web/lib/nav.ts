export interface NavItem {
  label: string;
  href: string;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Today", href: "/" },
  { label: "Content", href: "/content" },
  { label: "Research", href: "/research" },
  { label: "Network", href: "/network" },
  { label: "Jobs", href: "/jobs" },
  { label: "Applications", href: "/applications" },
  { label: "Analytics", href: "/analytics" },
  { label: "Automations", href: "/automations" },
  { label: "Settings", href: "/settings" },
];
