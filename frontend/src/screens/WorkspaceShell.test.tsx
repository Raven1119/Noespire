import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import type { WorkspaceReadModel } from "../types";
import { WorkspaceShell } from "./WorkspaceShell";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function readModel(overrides: Partial<WorkspaceReadModel>): WorkspaceReadModel {
  return {
    problem_id: "p-1",
    statement: "Every even perfect number is triangular.",
    status: "OPEN",
    display_status: "OPEN",
    derived_from: null,
    archived: false,
    obligation: null,
    attempts: [],
    target_fact: null,
    supporting_closure: [],
    running_phase_hint: null,
    ...overrides,
  };
}

function renderWorkspace(id = "p-1") {
  return render(
    <MemoryRouter initialEntries={[`/problems/${id}`]}>
      <Routes>
        <Route path="/problems/:problemId" element={<WorkspaceShell />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("WorkspaceShell", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders the statement, status badge, and the Proof | Attempts tab bar", async () => {
    mockedApi.getProblem.mockResolvedValue(readModel({}));
    renderWorkspace();

    expect(
      await screen.findByText("Every even perfect number is triangular.")
    ).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Proof" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Attempts" })).toBeTruthy();
    expect(
      screen.getByText("Attempts appear here once the first attempt has run.")
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "← Problems" })).toBeTruthy();
  });

  it("defaults to the Proof tab and shows the LLM-verified badge when SOLVED", async () => {
    mockedApi.getProblem.mockResolvedValue(
      readModel({ status: "SOLVED", display_status: "SOLVED" })
    );
    renderWorkspace();

    expect(await screen.findByText("LLM-verified")).toBeTruthy();
    expect(
      screen.getByRole("tab", { name: "Proof" }).getAttribute("aria-selected")
    ).toBe("true");
    expect(
      screen.getByText(
        "The proof document appears here once the problem is solved."
      )
    ).toBeTruthy();
  });

  it("never shows the LLM-verified badge when not SOLVED", async () => {
    mockedApi.getProblem.mockResolvedValue(
      readModel({ status: "OPEN", display_status: "ERROR" })
    );
    renderWorkspace();

    expect(await screen.findByText("Error")).toBeTruthy();
    expect(screen.queryByText("LLM-verified")).toBeNull();
  });

  it("shows an honest not-found message on 404", async () => {
    mockedApi.getProblem.mockRejectedValue(
      new api.ApiError(404, "unknown problem: p-missing")
    );
    renderWorkspace("p-missing");

    expect(await screen.findByText("Problem not found.")).toBeTruthy();
  });
});
