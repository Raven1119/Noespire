import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MathParagraphs, MathText } from "../components/MathText";

const NAMES = new Map([
  ["1111111111111111", "Lemma 1"],
  ["ffffffffffffffff", "Main theorem"],
]);

describe("MathText", () => {
  it("renders plain prose untouched", () => {
    const { container } = render(<MathText text="Every even perfect number is triangular." />);
    expect(container.textContent).toBe("Every even perfect number is triangular.");
    expect(container.querySelector(".katex")).toBeNull();
  });

  it("renders inline $…$ math through KaTeX", () => {
    const { container } = render(<MathText text="Then $n = T_{2^p - 1}$ holds." />);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.textContent).toContain("Then");
    expect(container.textContent).toContain("holds.");
  });

  it("renders display $$…$$ math in display mode", () => {
    const { container } = render(
      <MathText text={"Hence:\n\n$$T_{2^p - 1} = 2^{p-1}(2^p - 1)$$"} />
    );
    const display = container.querySelector(".katex-display");
    expect(display).not.toBeNull();
  });

  it("invalid LaTeX falls back to readable source text and never crashes", () => {
    const { container } = render(<MathText text="Broken $\\bogus{math here} end." />);
    expect(container.textContent).toContain("\\bogus");
    expect(container.textContent).toContain("end.");
  });

  it("replaces known fact ids with clickable math-styled references", () => {
    const onFactRef = vi.fn();
    render(
      <MathText
        text="By 1111111111111111 the number is even, and 1111111111111111 again."
        factNames={NAMES}
        onFactRef={onFactRef}
      />
    );

    const refs = screen.getAllByRole("button", { name: "Lemma 1" });
    expect(refs).toHaveLength(2);
    fireEvent.click(refs[0]);
    expect(onFactRef).toHaveBeenCalledWith("1111111111111111");
    // The raw id is gone from the rendered text.
    expect(screen.queryByText(/1111111111111111/)).toBeNull();
  });

  it("leaves unknown ids as plain text", () => {
    const { container } = render(
      <MathText text="See 9999999999999999 for details." factNames={NAMES} />
    );
    expect(container.textContent).toContain("9999999999999999");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("without a fact-name map, ids stay plain text", () => {
    const { container } = render(<MathText text="By 1111111111111111 we conclude." />);
    expect(container.textContent).toContain("1111111111111111");
  });
});

describe("MathParagraphs", () => {
  it("splits the proof body on blank lines into paragraphs", () => {
    const { container } = render(
      <MathParagraphs text={"First paragraph.\n\nSecond paragraph.\n\n\nThird."} />
    );
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(3);
    expect(paragraphs[1].textContent).toBe("Second paragraph.");
  });
});
