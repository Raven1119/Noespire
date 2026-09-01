import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  makeModel,
  runningGeneratingModel,
} from "../test-support/workspaceFixtures";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
    listProblems: vi.fn(),
    forkProblem: vi.fn(),
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

function forkResponse(id = "p-child") {
  return {
    problem_id: id,
    statement: "Revised child statement.",
    status: "OPEN" as const,
    derived_from: "p-1",
    archived: false,
  };
}

describe("Fork dialog — mechanics", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
  });

  it("opens prefilled with the current statement and closes via Cancel and Esc", async () => {
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    const dialog = screen.getByRole("dialog", { name: "Revise & Fork" });
    const textarea = screen.getByLabelText("Fork statement") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Every even perfect number is triangular.");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(dialog).toBeTruthy();
  });

  it("moves focus into the dialog and back to the trigger on close", async () => {
    await renderWorkspace();

    const trigger = screen.getByRole("button", { name: "Revise & Fork" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByLabelText("Fork statement")).toBe(document.activeElement);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(trigger);
  });

  it("blocks a blank fork client-side", async () => {
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    const textarea = screen.getByLabelText("Fork statement");
    fireEvent.change(textarea, { target: { value: "   " } });

    const submit = screen.getByRole("button", {
      name: "Create fork",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(mockedApi.forkProblem).not.toHaveBeenCalled();
  });

  it("allows an identical statement (fork is version identity, not a diff)", async () => {
    mockedApi.forkProblem.mockResolvedValue(forkResponse());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    const submit = screen.getByRole("button", {
      name: "Create fork",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });
});

describe("Fork dialog — submission", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
    mockedApi.getProblem.mockImplementation((id: string) =>
      Promise.resolve(
        id === "p-child"
          ? makeModel({
              problem_id: "p-child",
              statement: "Revised child statement.",
              derived_from: "p-1",
            })
          : makeModel({})
      )
    );
  });

  async function openAndSubmit() {
    await renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    fireEvent.change(screen.getByLabelText("Fork statement"), {
      target: { value: "Revised child statement." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create fork" }));
  }

  it("calls the api and navigates to the new problem on 201", async () => {
    mockedApi.forkProblem.mockResolvedValue(forkResponse());
    await openAndSubmit();

    expect(mockedApi.forkProblem).toHaveBeenCalledWith(
      "p-1",
      "Revised child statement."
    );
    expect(
      await screen.findByText("Revised child statement.")
    ).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the 400 message inline and keeps the dialog open", async () => {
    mockedApi.forkProblem.mockRejectedValue(
      new api.ApiError(400, "statement must be non-empty")
    );
    await openAndSubmit();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "statement must be non-empty"
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("shows the 404 message inline and keeps the dialog open", async () => {
    mockedApi.forkProblem.mockRejectedValue(
      new api.ApiError(404, "unknown problem: p-1")
    );
    await openAndSubmit();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "unknown problem: p-1"
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("shows an honest error on network failure and keeps the dialog open", async () => {
    mockedApi.forkProblem.mockRejectedValue(
      new api.ApiError(null, "Could not reach the Noespire server.")
    );
    await openAndSubmit();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Could not reach the Noespire server."
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("a RUNNING parent can fork — execution is never blocked or stopped", async () => {
    mockedApi.getProblem.mockImplementation((id: string) =>
      Promise.resolve(
        id === "p-child"
          ? makeModel({ problem_id: "p-child", statement: "Revised child statement." })
          : runningGeneratingModel()
      )
    );
    mockedApi.forkProblem.mockResolvedValue(forkResponse());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Revise & Fork" }));
    fireEvent.change(screen.getByLabelText("Fork statement"), {
      target: { value: "Revised child statement." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create fork" }));

    expect(mockedApi.forkProblem).toHaveBeenCalledWith(
      "p-1",
      "Revised child statement."
    );
    expect(await screen.findByText("Revised child statement.")).toBeTruthy();
  });
});
