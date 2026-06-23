import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  it("renders the prototype brand mark and sticky header content", () => {
    render(<AppHeader />);

    expect(screen.getByRole("link", { name: "AI World Radar 首页" })).toBeInTheDocument();
    expect(screen.getByText("AI World Radar")).toHaveClass("brand-name");
    expect(screen.getByText("2026.06.23")).toBeInTheDocument();
  });
});
