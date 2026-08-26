import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell/AppShell";
import { NAV_ITEMS } from "@/lib/nav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("AppShell", () => {
  it("renders children inside the main content area", () => {
    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );
    expect(screen.getByText("page content")).toBeInTheDocument();
  });

  it("derives the page title from the current route", () => {
    render(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByRole("heading", { name: "Command Center" })).toBeInTheDocument();
  });

  it("shows a mock-data indicator rather than presenting placeholder data as live", () => {
    render(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByText(/MOCK DATA/i)).toBeInTheDocument();
  });
});

describe("Navigation", () => {
  it("renders a link for every screen in the screen map", () => {
    render(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );
    const nav = screen.getByTestId("sidebar-nav");
    for (const item of NAV_ITEMS) {
      const link = screen.getByRole("link", { name: item.label });
      expect(link).toHaveAttribute("href", item.href);
      expect(nav).toContainElement(link);
    }
  });

  it("marks the active route with aria-current", () => {
    render(
      <AppShell>
        <p>content</p>
      </AppShell>,
    );
    const activeLink = screen.getByRole("link", { name: "Command Center" });
    expect(activeLink).toHaveAttribute("aria-current", "page");

    const inactiveLink = screen.getByRole("link", { name: "Markets" });
    expect(inactiveLink).not.toHaveAttribute("aria-current");
  });
});
