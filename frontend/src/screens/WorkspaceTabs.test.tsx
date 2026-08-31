import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { POLL_INTERVAL_MS } from "./useWorkspacePolling";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  errorModel,
  makeModel,
  runningGeneratingModel,
  solvedMultiFactModel,
} from "../test-support/workspaceFixtures";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
    listProblems: vi.fn(),
    startAttempt: vi.fn(),
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

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

function selectedTab(name: string): boolean {
  return screen.getByRole("tab", { name }).getAttribute("aria-selected") === "true";
}

describe("WorkspaceShell — default tab per state (applied on initial load only)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("SOLVED defaults to the Proof tab", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();
    expect(selectedTab("Proof")).toBe(true);
  });

  it("OPEN defaults to the Attempts tab", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    await renderWorkspace();
    expect(selectedTab("Attempts")).toBe(true);
  });

  it("RUNNING defaults to the Attempts tab", async () => {
    mockedApi.getProblem.mockResolvedValue(runningGeneratingModel());
    await renderWorkspace();
    expect(selectedTab("Attempts")).toBe(true);
  });

  it("ERROR display state defaults to the Attempts tab", async () => {
    mockedApi.getProblem.mockResolvedValue(errorModel());
    await renderWorkspace();
    expect(selectedTab("Attempts")).toBe(true);
  });
});

describe("WorkspaceShell — user tab ownership", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("a manual tab choice survives polling ticks", async () => {
    mockedApi.getProblem.mockResolvedValue(runningGeneratingModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Proof" }));
    expect(selectedTab("Proof")).toBe(true);

    await advance(POLL_INTERVAL_MS);
    await advance(POLL_INTERVAL_MS);
    expect(selectedTab("Proof")).toBe(true);
  });

  it("RUNNING → SOLVED does not yank the user from Attempts to Proof", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(runningGeneratingModel())
      .mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();
    expect(selectedTab("Attempts")).toBe(true);

    await advance(POLL_INTERVAL_MS); // lands SOLVED

    expect(selectedTab("Attempts")).toBe(true);
  });

  it("RUNNING → SOLVED keeps a manually chosen Proof tab", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(runningGeneratingModel())
      .mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("tab", { name: "Proof" }));
    await advance(POLL_INTERVAL_MS); // lands SOLVED

    expect(selectedTab("Proof")).toBe(true);
  });
});
