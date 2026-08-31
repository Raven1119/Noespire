import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import type { ProblemSummary } from "../types";
import { Home } from "./Home";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    listProblems: vi.fn(),
    createProblem: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function summary(overrides: Partial<ProblemSummary>): ProblemSummary {
  return {
    problem_id: "problem-1",
    statement: "Every even perfect number is triangular.",
    status: "OPEN",
    display_status: "OPEN",
    attempt_count: 0,
    derived_from: null,
    archived: false,
    last_activity: null,
    ...overrides,
  };
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route
          path="/problems/:problemId"
          element={<div>Workspace for problem</div>}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("Home", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders fetched problems with status, attempt count, and lineage", async () => {
    mockedApi.listProblems.mockResolvedValue({
      problems: [
        summary({
          problem_id: "p-open",
          statement: "Every even perfect number is triangular.",
          attempt_count: 2,
        }),
        summary({
          problem_id: "p-solved",
          statement: "For $n > 2$, $x^n + y^n = z^n$ has no solutions.",
          status: "SOLVED",
          display_status: "SOLVED",
          attempt_count: 1,
          derived_from: "p-open",
        }),
      ],
    });
    renderHome();

    expect(
      await screen.findByText("Every even perfect number is triangular.")
    ).toBeTruthy();
    expect(screen.getByText("has no solutions.")).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByText("Solved")).toBeTruthy();
    expect(screen.getByText("2 attempts")).toBeTruthy();
    expect(screen.getByText("1 attempt")).toBeTruthy();
    expect(screen.getByText("Derived from p-open")).toBeTruthy();
  });

  it("shows the empty state when there are no problems", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    renderHome();

    expect(await screen.findByText("No problems yet.")).toBeTruthy();
    expect(
      screen.getByText("Create your first mathematical problem.")
    ).toBeTruthy();
  });

  it("shows an honest error with a retry affordance when the server is unreachable", async () => {
    mockedApi.listProblems.mockRejectedValue(
      new api.ApiError(
        null,
        "Could not reach the Noespire server. Check that it is running and try again."
      )
    );
    renderHome();

    expect(await screen.findByText("Could not load problems")).toBeTruthy();
    expect(
      screen.getByText(/Could not reach the Noespire server/)
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("opens the New Problem form", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    renderHome();

    fireEvent.click(
      screen.getByRole("button", { name: "+ New Problem" })
    );

    expect(
      await screen.findByLabelText(
        "Mathematical problem / theorem statement"
      )
    ).toBeTruthy();
  });

  it("submits the normalized statement to the api", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.createProblem.mockResolvedValue({
      problem_id: "new-problem",
      statement: "Every even perfect number is triangular.",
      status: "OPEN",
      derived_from: null,
      archived: false,
    });
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: "+ New Problem" }));
    fireEvent.change(
      await screen.findByLabelText("Mathematical problem / theorem statement"),
      { target: { value: "  Every even perfect number is triangular.  " } }
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Problem" }));

    // Wait for the async submit to settle (navigation to the workspace).
    await screen.findByText("Workspace for problem");
    expect(mockedApi.createProblem).toHaveBeenCalledWith(
      "Every even perfect number is triangular."
    );
  });

  it("navigates to the new problem's workspace on success", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.createProblem.mockResolvedValue({
      problem_id: "new-problem",
      statement: "Every even perfect number is triangular.",
      status: "OPEN",
      derived_from: null,
      archived: false,
    });
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: "+ New Problem" }));
    fireEvent.change(
      await screen.findByLabelText("Mathematical problem / theorem statement"),
      { target: { value: "Every even perfect number is triangular." } }
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Problem" }));

    expect(await screen.findByText("Workspace for problem")).toBeTruthy();
  });

  it("shows the server's validation message near the field on 400", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.createProblem.mockRejectedValue(
      new api.ApiError(400, "statement must not be blank")
    );
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: "+ New Problem" }));
    fireEvent.change(
      await screen.findByLabelText("Mathematical problem / theorem statement"),
      { target: { value: "   " } }
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Problem" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("statement must not be blank");
  });

  it("shows an honest error on other server failures", async () => {
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.createProblem.mockRejectedValue(
      new api.ApiError(500, "Request failed with status 500.")
    );
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: "+ New Problem" }));
    fireEvent.change(
      await screen.findByLabelText("Mathematical problem / theorem statement"),
      { target: { value: "Every even perfect number is triangular." } }
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Problem" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Request failed with status 500.");
  });

  it("hides archived problems by default and shows them behind the toggle", async () => {
    mockedApi.listProblems.mockResolvedValue({
      problems: [
        summary({
          problem_id: "p-live",
          statement: "Every even perfect number is triangular.",
        }),
        summary({
          problem_id: "p-archived",
          statement: "An archived conjecture about primes.",
          archived: true,
        }),
      ],
    });
    renderHome();

    expect(
      await screen.findByText("Every even perfect number is triangular.")
    ).toBeTruthy();
    expect(screen.queryByText("An archived conjecture about primes.")).toBeNull();

    fireEvent.click(screen.getByLabelText("Show archived"));

    expect(
      screen.getByText("An archived conjecture about primes.")
    ).toBeTruthy();
  });
});
