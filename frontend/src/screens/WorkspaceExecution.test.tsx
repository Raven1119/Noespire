import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import type { Attempt, WorkspaceReadModel } from "../types";
import { POLL_INTERVAL_MS } from "./useWorkspacePolling";
import { WorkspaceShell } from "./WorkspaceShell";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
    startAttempt: vi.fn(),
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

function attempt(overrides: Partial<Attempt>): Attempt {
  return {
    attempt_id: "attempt-000007",
    verdict: "RUNNING",
    failure_class: null,
    candidate: null,
    verifier: null,
    error: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

const runningModel = () =>
  readModel({
    status: "RUNNING",
    display_status: "RUNNING",
    attempts: [attempt({})],
    running_phase_hint: "generating",
    live: { running: true, current_attempt_id: "attempt-000007" },
  });

async function renderAndFlush(id = "p-1") {
  render(
    <MemoryRouter initialEntries={[`/problems/${id}`]}>
      <Routes>
        <Route path="/problems/:problemId" element={<WorkspaceShell />} />
      </Routes>
    </MemoryRouter>
  );
  await act(async () => {});
}

async function flush() {
  await act(async () => {});
}

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

async function clickStart(name: string | RegExp = "Start proving") {
  fireEvent.click(screen.getByRole("button", { name }));
  await flush();
}

describe("WorkspaceShell — Slice 3 execution", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls startAttempt on click and begins polling after a 202", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(readModel({}))
      .mockResolvedValue(runningModel());
    mockedApi.startAttempt.mockResolvedValue({ status: "accepted" });
    await renderAndFlush();

    await clickStart();
    expect(mockedApi.startAttempt).toHaveBeenCalledTimes(1);
    expect(mockedApi.startAttempt).toHaveBeenCalledWith("p-1");
    // Initial load + the post-202 refetch that picks up RUNNING.
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Generating candidate…")).toBeTruthy();

    await advance(POLL_INTERVAL_MS);
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(3);
    await advance(POLL_INTERVAL_MS);
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(4);
  });

  it("labels the action Retry once attempts exist", async () => {
    mockedApi.getProblem.mockResolvedValue(
      readModel({
        attempts: [attempt({ verdict: "FAIL", failure_class: "rejection" })],
      })
    );
    mockedApi.startAttempt.mockResolvedValue({ status: "accepted" });
    await renderAndFlush();

    await clickStart("Retry");
    expect(mockedApi.startAttempt).toHaveBeenCalledWith("p-1");
  });

  it("disables the action with an honest hint while RUNNING", async () => {
    mockedApi.getProblem.mockResolvedValue(runningModel());
    await renderAndFlush();

    const button = screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("An attempt is already running.")).toBeTruthy();

    fireEvent.click(button);
    await flush();
    expect(mockedApi.startAttempt).not.toHaveBeenCalled();
  });

  it("shows no start action when SOLVED", async () => {
    mockedApi.getProblem.mockResolvedValue(
      readModel({ status: "SOLVED", display_status: "SOLVED" })
    );
    await renderAndFlush();

    expect(screen.queryByRole("button", { name: /start attempt|retry/i })).toBeNull();
  });

  it("polls while RUNNING and stops exactly when a terminal state arrives", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(runningModel())
      .mockResolvedValueOnce(runningModel())
      .mockResolvedValue(readModel({ status: "SOLVED", display_status: "SOLVED" }));
    await renderAndFlush();
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(1);

    await advance(POLL_INTERVAL_MS); // still RUNNING
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Generating candidate…")).toBeTruthy();

    await advance(POLL_INTERVAL_MS); // lands on SOLVED → terminal
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(3);
    expect(screen.queryByText("Generating candidate…")).toBeNull();

    await advance(POLL_INTERVAL_MS * 4); // no further polling
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(3);
  });

  it("begins polling anyway on 409 already_running", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(readModel({}))
      .mockResolvedValue(runningModel());
    mockedApi.startAttempt.mockRejectedValue(
      new api.ApiError(409, "already_running", "already_running")
    );
    await renderAndFlush();

    await clickStart();
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();

    await advance(POLL_INTERVAL_MS);
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(3);
  });

  it("does a single refetch and no polling on 409 already_solved", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(readModel({}))
      .mockResolvedValue(readModel({ status: "SOLVED", display_status: "SOLVED" }));
    mockedApi.startAttempt.mockRejectedValue(
      new api.ApiError(409, "already_solved", "already_solved")
    );
    await renderAndFlush();

    await clickStart();
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Solved")).toBeTruthy();

    await advance(POLL_INTERVAL_MS * 4);
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(2);
  });

  it("renders the phase line with the 'phase inferred' marker", async () => {
    mockedApi.getProblem.mockResolvedValue(
      readModel({
        ...runningModel(),
        running_phase_hint: "checking",
      })
    );
    await renderAndFlush();

    expect(screen.getByText("Checking candidate…")).toBeTruthy();
    expect(screen.getByText("live · phase inferred")).toBeTruthy();
  });

  it("runs a session-scoped elapsed clock that vanishes on terminal states", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(runningModel())
      .mockResolvedValue(readModel({ status: "OPEN", display_status: "OPEN" }));
    await renderAndFlush();

    expect(screen.getByText("00:00 on this page")).toBeTruthy();
    await advance(1000); // before the first poll tick
    expect(screen.getByText("00:01 on this page")).toBeTruthy();
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(1);

    await advance(POLL_INTERVAL_MS); // poll lands on OPEN → terminal
    expect(screen.queryByText(/on this page/)).toBeNull();
  });

  it("shows the latest attempt verdict and failure class after landing on OPEN", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(runningModel())
      .mockResolvedValue(
        readModel({
          attempts: [attempt({ verdict: "FAIL", failure_class: "rejection" })],
        })
      );
    await renderAndFlush();

    await advance(POLL_INTERVAL_MS);
    expect(
      screen.getByRole("button", { name: /Attempt 1\b/ })
    ).toBeTruthy();
    expect(screen.getByText(/Verification rejection/)).toBeTruthy();
  });

  it("shows an honest inline error on 404 from startAttempt", async () => {
    mockedApi.getProblem.mockResolvedValue(readModel({}));
    mockedApi.startAttempt.mockRejectedValue(
      new api.ApiError(404, "unknown problem: p-1")
    );
    await renderAndFlush();

    await clickStart();
    expect(screen.getByRole("alert").textContent).toContain(
      "The server does not know this problem (404)."
    );
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(1); // no refetch

    await advance(POLL_INTERVAL_MS * 4); // and no polling
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(1);
  });

  it("shows the server error inline when the start request fails", async () => {
    mockedApi.getProblem.mockResolvedValue(readModel({}));
    mockedApi.startAttempt.mockRejectedValue(
      new api.ApiError(
        null,
        "Could not reach the Noespire server. Check that it is running and try again."
      )
    );
    await renderAndFlush();

    await clickStart();
    expect(screen.getByRole("alert").textContent).toContain(
      "Could not reach the Noespire server."
    );
    expect(mockedApi.getProblem).toHaveBeenCalledTimes(1);
  });
});
