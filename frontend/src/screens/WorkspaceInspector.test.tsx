import { useState } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { InspectorDrawer } from "../inspector/InspectorDrawer";
import { WorkspaceShell } from "./WorkspaceShell";
import { makeModel, solvedMultiFactModel } from "../test-support/workspaceFixtures";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
    listProblems: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

async function renderWorkspace(id = "p-1") {
  render(
    <MemoryRouter initialEntries={[`/problems/${id}`]}>
      <Routes>
        <Route path="/problems/:problemId" element={<WorkspaceShell />} />
      </Routes>
    </MemoryRouter>
  );
  await act(async () => {});
}

describe("InspectorDrawer — drawer mechanics (component seam)", () => {
  const fields = [{ label: "problem_id", value: "p-1", mono: true }];
  const raw = { problem_id: "p-1" };

  it("is a labelled dialog with a labelled close button and collapsed raw JSON", () => {
    render(
      <InspectorDrawer title="Problem" fields={fields} raw={raw} onClose={() => {}} />
    );

    const dialog = screen.getByRole("dialog", { name: "Problem" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByRole("button", { name: "Close inspector" })).toBeTruthy();
    expect(screen.getByText("problem_id")).toBeTruthy();
    // Raw JSON is collapsed behind a disclosure, not mounted open.
    const disclosure = screen.getByText("Raw JSON");
    const details = disclosure.closest("details") as HTMLDetailsElement;
    expect(details.hasAttribute("open")).toBe(false);
    expect(screen.queryByText(/"p-1"/)).toBeNull();
    // jsdom does not implement summary's native toggle; set open + dispatch.
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(screen.getByText(/"problem_id": "p-1"/)).toBeTruthy();
  });

  it("moves focus into the drawer on open and back to the trigger on close", () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>trigger</button>
          {open && (
            <InspectorDrawer
              title="Problem"
              fields={fields}
              raw={raw}
              onClose={() => setOpen(false)}
            />
          )}
        </>
      );
    }
    render(<Harness />);

    const trigger = screen.getByRole("button", { name: "trigger" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Problem" });
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Close inspector" }));
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<InspectorDrawer title="Problem" fields={fields} raw={raw} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the scrim is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <InspectorDrawer title="Problem" fields={fields} raw={raw} onClose={onClose} />
    );

    fireEvent.click(container.querySelector(".inspector-scrim") as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("WorkspaceShell — Problem inspector (header ⓘ)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("opens the Problem inspector from the header and closes via Esc", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    const dialog = await screen.findByRole("dialog", { name: "Problem" });
    expect(dialog.textContent).toContain("p-1");
    expect(dialog.textContent).toContain("OPEN");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("switches objects: opening the inspector again replaces the content", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    expect(await screen.findByRole("dialog", { name: "Problem" })).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    expect(await screen.findByRole("dialog", { name: "Problem" })).toBeTruthy();
  });
});

describe("WorkspaceShell — Fact inspector (proof document ⓘ)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("shows fact_id, predecessors, and statement — never an author", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    // Focus Lemma 1 via its closure entry, then open its inspector.
    const closure = document.querySelector(".closure-list") as HTMLElement;
    fireEvent.click(within(closure).getAllByRole("button")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Lemma 1" }));

    const dialog = await screen.findByRole("dialog", { name: "Fact" });
    expect(dialog.textContent).toContain("1111111111111111");
    expect(dialog.textContent).toContain("predecessors");
    expect(dialog.textContent).toContain("Every even perfect number");
    expect(dialog.textContent).not.toContain("author");
  });

  it("switches from the Problem inspector to the Fact inspector", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    expect(await screen.findByRole("dialog", { name: "Problem" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });

    const closure = document.querySelector(".closure-list") as HTMLElement;
    fireEvent.click(within(closure).getAllByRole("button")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Lemma 1" }));
    expect(await screen.findByRole("dialog", { name: "Fact" })).toBeTruthy();
  });
});
