import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  LEMMA_ONE,
  LEMMA_TWO,
  MAIN_FACT,
  makeModel,
  runningCheckingModel,
  solvedMultiFactModel,
  solvedSingleFactModel,
} from "../test-support/workspaceFixtures";

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

describe("Proof tab — SOLVED", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("renders the proof document: statement, proof body, LLM-verified badge", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    const panel = screen.getByRole("tabpanel");
    expect(panel.textContent).toContain("Every even perfect number is triangular.");
    expect(panel.textContent).toContain("Let");
    expect(panel.textContent).toContain("Therefore");
    expect(panel.querySelector(".katex")).not.toBeNull();
    expect(panel.textContent).toContain("LLM-verified");
    // Machine ids never appear in the proof document body.
    expect(panel.textContent).not.toContain(LEMMA_ONE.fact_id);
    expect(panel.textContent).not.toContain(MAIN_FACT.fact_id);
  });

  it("lists the supporting closure as named Lemmas in topo order", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    const closure = document.querySelector(".closure-list");
    expect(closure).not.toBeNull();
    const closureItems = within(closure as HTMLElement).getAllByRole("button");
    expect(closureItems.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Lemma 1"),
      expect.stringContaining("Lemma 2"),
      expect.stringContaining("Main theorem"),
    ] as unknown as string[]);
    expect(closureItems[0].textContent).toContain(LEMMA_ONE.statement.replace(/\$|\\mid/g, "").slice(0, 20).trim().split(" ")[0]);
  });

  it("navigates in place: inline fact reference → lemma document → back", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    const panel = screen.getByRole("tabpanel");
    // The proof text references the lemmas by name, not by id.
    const inlineRefs = screen
      .getAllByRole("button", { name: "Lemma 2" })
      .filter((b) => b.closest(".proof-document") !== null);
    expect(inlineRefs.length).toBeGreaterThan(0);
    fireEvent.click(inlineRefs[0]);

    // Focused lemma document with a back link.
    expect(screen.getByRole("button", { name: "← Back to main theorem" })).toBeTruthy();
    expect(panel.textContent).toContain("The triangular identity is exact.");

    fireEvent.click(screen.getByRole("button", { name: "← Back to main theorem" }));
    expect(panel.textContent).toContain("Therefore");
  });

  it("navigates from a closure list item to that Fact's document", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    const closure = document.querySelector(".closure-list");
    expect(closure).not.toBeNull();
    const closureItems = within(closure as HTMLElement).getAllByRole("button");
    fireEvent.click(closureItems[0]);

    const panel = screen.getByRole("tabpanel");
    expect(panel.textContent).toContain("By definition an even perfect number is even.");
    expect(screen.getByRole("button", { name: "← Back to main theorem" })).toBeTruthy();
  });

  it("a single-fact closure renders the one-line note instead of a list", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedSingleFactModel());
    await renderWorkspace();

    expect(
      screen.getByText("This proof has no supporting Fact dependencies.")
    ).toBeTruthy();
    expect(document.querySelector(".closure-list")).toBeNull();
  });
});

describe("Proof tab — unsolved", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("OPEN shows the honest empty state", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Proof" }));
    expect(screen.getByText("No verified proof yet")).toBeTruthy();
    expect(screen.getByText(/Attempts tab/)).toBeTruthy();
  });

  it("RUNNING never leaks the candidate into the Proof tab", async () => {
    mockedApi.getProblem.mockResolvedValue(runningCheckingModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Proof" }));
    expect(screen.getByText("No verified proof yet")).toBeTruthy();
    const panel = screen.getByRole("tabpanel");
    expect(panel.textContent).not.toContain("Let $n = 2^{p-1}(2^p - 1)$.");
    expect(panel.querySelector(".katex")).toBeNull();
  });
});
