import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  makeModel,
  solvedMultiFactModel,
} from "../test-support/workspaceFixtures";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getProblem: vi.fn(),
    listProblems: vi.fn(),
    setProblemArchived: vi.fn(),
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

describe("Archive / Unarchive", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("archives in place: api call, Archived badge, button flips — status badge unchanged", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(makeModel({}))
      .mockResolvedValue(makeModel({ archived: true }));
    mockedApi.setProblemArchived.mockResolvedValue({ archived: true });
    await renderWorkspace();

    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.queryByText("Archived")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Archive" }));

    expect(mockedApi.setProblemArchived).toHaveBeenCalledWith("p-1", true);
    expect(await screen.findByText("Archived")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Unarchive" })).toBeTruthy();
    // The main status badge is orthogonal: still Open.
    expect(screen.getByText("Open")).toBeTruthy();
  });

  it("unarchives an archived problem", async () => {
    mockedApi.getProblem
      .mockResolvedValueOnce(makeModel({ archived: true }))
      .mockResolvedValue(makeModel({}));
    mockedApi.setProblemArchived.mockResolvedValue({ archived: false });
    await renderWorkspace();

    expect(screen.getByText("Archived")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Unarchive" }));

    expect(mockedApi.setProblemArchived).toHaveBeenCalledWith("p-1", false);
    await act(async () => {});
    expect(screen.queryByText("Archived")).toBeNull();
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
  });

  it("a SOLVED problem keeps its Solved badge when archived", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    // solvedMultiFactModel is not archived; render an archived variant instead.
    mockedApi.getProblem.mockResolvedValue({
      ...solvedMultiFactModel(),
      archived: true,
    });
    await renderWorkspace();

    expect(screen.getByText("Solved")).toBeTruthy();
    expect(screen.getByText("Archived")).toBeTruthy();
    // Header badge + proof document badge both carry the mark.
    expect(screen.getAllByText("LLM-verified").length).toBeGreaterThan(0);
  });

  it("disables the button while the mutation is in flight", async () => {
    let resolveMutation: (value: { archived: boolean }) => void = () => {};
    mockedApi.setProblemArchived.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMutation = resolve;
        })
    );
    mockedApi.getProblem
      .mockResolvedValueOnce(makeModel({}))
      .mockResolvedValue(makeModel({ archived: true }));
    await renderWorkspace();

    const button = screen.getByRole("button", {
      name: "Archive",
    }) as HTMLButtonElement;
    fireEvent.click(button);
    expect(button.disabled).toBe(true);

    resolveMutation({ archived: true });
    await act(async () => {});
    expect(
      (screen.getByRole("button", { name: "Unarchive" }) as HTMLButtonElement)
        .disabled
    ).toBe(false);
  });

  it("shows an honest inline error and leaves the state unchanged on failure", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    mockedApi.setProblemArchived.mockRejectedValue(
      new api.ApiError(null, "Could not reach the Noespire server.")
    );
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Archive" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Could not reach the Noespire server."
    );
    expect(screen.queryByText("Archived")).toBeNull();
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
  });
});
