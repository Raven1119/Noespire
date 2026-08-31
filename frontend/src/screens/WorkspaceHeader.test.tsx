import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  errorModel,
  interruptedModel,
  makeModel,
  openRejectionModel,
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

describe("WorkspaceShell — header actions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("fresh OPEN (no attempts) offers 'Start proving'", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({ attempts: [] }));
    await renderWorkspace();

    const button = screen.getByRole("button", {
      name: "Start proving",
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it("OPEN with attempts offers 'Retry'", async () => {
    mockedApi.getProblem.mockResolvedValue(openRejectionModel());
    await renderWorkspace();

    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start proving" })).toBeNull();
  });

  it("ERROR display state offers 'Retry'", async () => {
    mockedApi.getProblem.mockResolvedValue(errorModel());
    await renderWorkspace();

    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("interrupted latest attempt offers 'Retry'", async () => {
    mockedApi.getProblem.mockResolvedValue(interruptedModel(false));
    await renderWorkspace();

    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("RUNNING disables Retry with an accessible 'already running' hint", async () => {
    mockedApi.getProblem.mockResolvedValue(runningGeneratingModel());
    await renderWorkspace();

    const button = screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("An attempt is already running.")).toBeTruthy();
  });

  it("SOLVED shows no Retry and keeps 'Revise & Fork' as a disabled stub", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();

    expect(screen.queryByRole("button", { name: /start proving|retry/i })).toBeNull();
    const fork = screen.getByRole("button", {
      name: "Revise & Fork",
    }) as HTMLButtonElement;
    expect(fork.disabled).toBe(true);
  });

  it("always shows the Inspector button", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    await renderWorkspace();

    expect(screen.getByRole("button", { name: "Open inspector" })).toBeTruthy();
  });
});

describe("WorkspaceShell — derived-from line", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("links to the parent with a statement snippet when the parent is known", async () => {
    mockedApi.getProblem.mockResolvedValue(
      makeModel({ derived_from: "p-parent" })
    );
    mockedApi.listProblems.mockResolvedValue({
      problems: [
        {
          problem_id: "p-parent",
          statement: "Every even perfect number is a triangular number.",
          status: "SOLVED",
          display_status: "SOLVED",
          attempt_count: 1,
          derived_from: null,
          archived: false,
          last_activity: null,
        },
      ],
    });
    await renderWorkspace();

    const link = (await screen.findByRole("link", {
      name: /triangular number/,
    })) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/problems/p-parent");
    expect(screen.getByText(/Derived from/)).toBeTruthy();
  });

  it("falls back to the plain-text id when the parent cannot be resolved", async () => {
    mockedApi.getProblem.mockResolvedValue(
      makeModel({ derived_from: "p-gone" })
    );
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    await renderWorkspace();

    expect((await screen.findByText(/Derived from/)).textContent).toContain("p-gone");
    expect(screen.queryByRole("link", { name: /p-gone/ })).toBeNull();
  });

  it("shows no derived-from line for a root problem", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({ derived_from: null }));
    await renderWorkspace();

    expect(screen.queryByText(/Derived from/)).toBeNull();
  });
});
