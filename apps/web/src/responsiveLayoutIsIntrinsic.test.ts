import { describe, expect, it } from "vitest";

const stylesheets = import.meta.glob(["./App.css", "./components/policyTests.css"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const CSS = Object.values(stylesheets).join("\n");

function declarationFor(selector: string, property: string): string | undefined {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = CSS.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "m"));
  if (!match) return undefined;
  const declarations = new Map(
    match[1]
      .split(";")
      .map((part) => part.split(":").map((piece) => piece.trim().toLowerCase()))
      .filter((parts): parts is [string, string] => parts.length === 2 && parts[0].length > 0),
  );
  return declarations.get(property);
}

describe("responsive layout rules are intrinsic", () => {
  it("does not reintroduce viewport-width media query breakpoints", () => {
    expect(CSS).not.toMatch(/@media\s*\(\s*(?:min|max)-width\s*:/i);
  });

  it("keeps dashboard metrics on content-sized tracks", () => {
    expect(declarationFor(".dashboard-pressure-strip", "grid-template-columns")).toContain(
      "repeat(auto-fit",
    );
    expect(declarationFor(".dashboard-pressure-strip", "grid-template-columns")).toContain(
      "minmax(min(",
    );
  });

  it("keeps validation panes growing evenly after they wrap", () => {
    expect(declarationFor(".validation-config-grid > .validation-policy-selector", "flex")).toBe(
      "1 1 min(520px, 100%)",
    );
    expect(declarationFor(".validation-config-grid > .validation-generator", "flex")).toBe(
      "1 1 min(340px, 100%)",
    );
  });
});
