import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Formula, Frac, Sup, Times } from "./Formula";

describe("Formula", () => {
  it("renders a labelled math span", () => {
    render(
      <Formula label="Power formula">
        <span>P</span>
      </Formula>,
    );
    const math = screen.getByRole("math", { name: "Power formula" });
    expect(math).toBeInTheDocument();
    expect(math).toHaveClass("formula");
  });
});

describe("Frac", () => {
  it("renders the numerator before the denominator in document order", () => {
    render(
      <Formula label="fraction">
        <Frac num={<span data-testid="num">A</span>} den={<span data-testid="den">B</span>} />
      </Formula>,
    );
    const num = screen.getByTestId("num");
    const den = screen.getByTestId("den");
    // eslint-disable-next-line no-bitwise
    expect(num.compareDocumentPosition(den) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("Sup", () => {
  it("renders children inside a <sup> element", () => {
    render(<Sup>2</Sup>);
    const sup = screen.getByText("2");
    expect(sup.tagName).toBe("SUP");
  });
});

describe("Times", () => {
  it("renders a multiplication sign padded with thin spaces", () => {
    render(<Times />);
    expect(screen.getByText(/×/)).toBeInTheDocument();
  });
});
