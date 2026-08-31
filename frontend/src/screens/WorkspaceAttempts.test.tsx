import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import {
  LEMMA_TWO,
  makeAttempt,
  makeModel,
  openContractModel,
  openRejectionModel,
  openUnclassifiedModel,
  errorModel,
  interruptedModel,
  runningCheckingModel,
  solvedMultiFactModel,
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

/** OPEN model with two failed attempts (rejection then contract). */
function twoAttemptModel() {
  return makeModel({
    attempts: [
      makeAttempt({
        attempt_id: "attempt-000001",
        verdict: "FAIL",
        failure_class: "rejection",
        candidate: {
          statement: "Every even perfect number is triangular.",
          proof: "First try.",
          predecessors: [LEMMA_TWO.fact_id],
        },
        verifier: { accepted: false, reason: "The triangular identity is not justified." },
      }),
      makeAttempt({
        attempt_id: "attempt-000002",
        verdict: "FAIL",
        failure_class: "contract",
        candidate: {
          statement: "Every even perfect number is a triangle number.",
          proof: "Second try.",
          predecessors: [],
        },
        verifier: {
          accepted: false,
          reason: "candidate statement does not match obligation goal",
        },
      }),
    ],
  });
}

describe("Attempts tab — ordering and disclosure", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("lists attempts newest-first with API-order ordinals", async () => {
    mockedApi.getProblem.mockResolvedValue(twoAttemptModel());
    await renderWorkspace();

    const second = screen.getByRole("button", { name: /^Attempt 2\b/ });
    const first = screen.getByRole("button", { name: /^Attempt 1\b/ });
    expect(
      second.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("expands only the latest attempt by default; toggling reveals earlier ones", async () => {
    mockedApi.getProblem.mockResolvedValue(twoAttemptModel());
    await renderWorkspace();

    // Latest (Attempt 2) expanded: its candidate is visible.
    expect(screen.getByText("Second try.")).toBeTruthy();
    // Earlier (Attempt 1) collapsed: its candidate is not rendered.
    expect(screen.queryByText("First try.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^Attempt 1\b/ }));
    expect(screen.getByText("First try.")).toBeTruthy();
  });

  it("renders the candidate in the unverified register — banner, no raw predecessor ids", async () => {
    mockedApi.getProblem.mockResolvedValue(twoAttemptModel());
    await renderWorkspace();

    const banner = screen.getAllByText("Unverified — candidate proof");
    expect(banner.length).toBeGreaterThan(0);
    const card = banner[0].closest(".candidate-card");
    expect(card).not.toBeNull();
    const panel = screen.getByRole("tabpanel");
    expect(panel.textContent).not.toContain(LEMMA_TWO.fact_id);
  });

  it("empty state when no attempt has run", async () => {
    mockedApi.getProblem.mockResolvedValue(makeModel({}));
    await renderWorkspace();

    expect(
      screen.getByText("Attempts appear here once the first attempt has run.")
    ).toBeTruthy();
  });
});

describe("Attempts tab — failure panels", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("rejection: verifier reason + retry suggestion", async () => {
    mockedApi.getProblem.mockResolvedValue(openRejectionModel());
    await renderWorkspace();

    expect(screen.getByText("Verification rejection")).toBeTruthy();
    expect(
      screen.getByText(/The triangular identity is not justified\./)
    ).toBeTruthy();
    expect(screen.getByText(/Suggested next: Retry/)).toBeTruthy();
  });

  it("contract: guard reason + verifier-never-called line", async () => {
    mockedApi.getProblem.mockResolvedValue(openContractModel());
    await renderWorkspace();

    expect(screen.getByText("Contract failure")).toBeTruthy();
    expect(
      screen.getByText(/candidate statement does not match obligation goal/)
    ).toBeTruthy();
    expect(screen.getByText(/the fresh verifier was never called/)).toBeTruthy();
  });

  it("runtime: error text + no-mathematical-content line", async () => {
    mockedApi.getProblem.mockResolvedValue(errorModel());
    await renderWorkspace();

    expect(screen.getByText("Runtime error")).toBeTruthy();
    expect(screen.getByText(/scripted worker error/)).toBeTruthy();
    expect(screen.getByText(/no mathematical content was produced/)).toBeTruthy();
  });

  it("interrupted before the verifier call says so", async () => {
    mockedApi.getProblem.mockResolvedValue(interruptedModel(false));
    await renderWorkspace();

    expect(screen.getByText("Interrupted")).toBeTruthy();
    expect(
      screen.getByText(/before the fresh verifier was called/)
    ).toBeTruthy();
  });

  it("interrupted after the verifier call says so", async () => {
    mockedApi.getProblem.mockResolvedValue(interruptedModel(true));
    await renderWorkspace();

    expect(screen.getByText("Interrupted")).toBeTruthy();
    expect(
      screen.getByText(/after the fresh verifier was called/)
    ).toBeTruthy();
  });

  it("unclassified FAIL shows an honest note, never an invented class", async () => {
    mockedApi.getProblem.mockResolvedValue(openUnclassifiedModel());
    await renderWorkspace();

    const panel = screen.getByRole("tabpanel");
    for (const label of [
      "Contract failure",
      "Verification rejection",
      "Runtime error",
      "Interrupted",
    ]) {
      expect(panel.textContent).not.toContain(label);
    }
    expect(screen.getByText(/no failure classification/)).toBeTruthy();
  });
});

describe("Attempts tab — verdict registers", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("PASS on a SOLVED problem keeps the candidate as the accepted historical artifact", async () => {
    mockedApi.getProblem.mockResolvedValue(solvedMultiFactModel());
    await renderWorkspace();
    fireEvent.click(screen.getByRole("tab", { name: "Attempts" }));

    expect(screen.getByText("Accepted")).toBeTruthy();
    expect(screen.getAllByText("LLM-verified").length).toBeGreaterThan(0);
    // The candidate is still shown — as the artifact that became the target
    // Fact, never under the Unverified banner (task card §19).
    expect(screen.queryByText("Unverified — candidate proof")).toBeNull();
    expect(screen.getByText(/Accepted candidate/)).toBeTruthy();
    expect(screen.getByText(/became the target Fact/)).toBeTruthy();
    expect(screen.getAllByText(/Every even perfect number is triangular/).length).toBeGreaterThan(0);
  });

  it("RUNNING shows the phase line marked as inferred", async () => {
    mockedApi.getProblem.mockResolvedValue(runningCheckingModel());
    await renderWorkspace();

    expect(screen.getByText("Checking candidate…")).toBeTruthy();
    expect(screen.getByText(/live · phase inferred/)).toBeTruthy();
  });
});

describe("Attempts tab — inspector wiring", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.listProblems.mockResolvedValue({ problems: [] });
  });

  it("per-attempt ⓘ opens the inspector on that attempt", async () => {
    mockedApi.getProblem.mockResolvedValue(twoAttemptModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Inspect attempt 1" }));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByText("attempt-000001")).toBeTruthy();

    fireEvent.click(within(drawer).getByRole("button", { name: "Close inspector" }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect attempt 2" }));
    expect(
      within(screen.getByRole("dialog")).getByText("attempt-000002")
    ).toBeTruthy();
  });
});
