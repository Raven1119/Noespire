import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { WorkspaceShell } from "./WorkspaceShell";
import { executionFailurePanel } from "../workspace/failureMeta";
import {
  LEMMA_ONE,
  LEMMA_TWO,
  SCAFFOLD_FACT_STEP,
  scaffoldArchitectFailureModel,
  scaffoldBlockedModel,
  scaffoldRunningModel,
  scaffoldSolvedModel,
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

function planRows(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>(".proof-plan__item")];
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedApi.listProblems.mockResolvedValue({ problems: [] });
});

describe("Proof plan — state truthfulness", () => {
  it("renders each node state truthfully in dependency order, target last", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldBlockedModel());
    await renderWorkspace();

    expect(screen.getByText("Proof plan")).toBeTruthy();
    const rows = planRows();
    expect(rows).toHaveLength(3);
    // lemma1 VERIFIED — the only row allowed verified-truth styling (ADR-0003).
    expect(within(rows[0]).getByText("LLM-verified")).toBeTruthy();
    expect(rows[1].textContent).toContain("Blocked");
    expect(rows[1].textContent).not.toContain("LLM-verified");
    // The target is PLANNED — not run, never styled as failed.
    expect(rows[2].textContent).toContain("Planned");
    expect(rows[2].textContent).not.toContain("Blocked");
    expect(within(rows[2]).getByText("Target")).toBeTruthy();
  });

  it("sorts nodes topologically even when they arrive sorted by node_id", async () => {
    // Arrival order a_step, b_target, c_base is NOT topological.
    mockedApi.getProblem.mockResolvedValue(scaffoldRunningModel());
    await renderWorkspace();

    const rows = planRows();
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("LLM-verified"); // c_base
    expect(rows[1].textContent).toContain("Running"); // a_step
    expect(rows[2].textContent).toContain("Planned"); // b_target
    expect(within(rows[2]).getByText("Target")).toBeTruthy();
  });
});

describe("Scaffold RUNNING", () => {
  it("names the single running node with the phase-inferred marker", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldRunningModel());
    await renderWorkspace();

    const phase = document.querySelector(".running-indicator__phase");
    expect(phase).not.toBeNull();
    expect(phase!.textContent).toContain("Checking");
    expect(phase!.textContent).toContain("For every integer");
    expect(phase!.textContent).toContain("live · phase inferred");
  });
});

describe("STATIC_SCAFFOLD SOLVED — Proof tab", () => {
  it("renders the real multi-Fact closure and in-place navigation", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldSolvedModel());
    await renderWorkspace();

    // SOLVED defaults to the Proof tab.
    const closure = document.querySelector(".closure-list");
    expect(closure).not.toBeNull();
    const items = within(closure as HTMLElement).getAllByRole("button");
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Lemma 1"),
      expect.stringContaining("Lemma 2"),
      expect.stringContaining("Main theorem"),
    ] as unknown as string[]);

    // In-place navigation to a lemma document and back.
    fireEvent.click(items[1]);
    const panel = screen.getByRole("tabpanel");
    expect(panel.textContent).toContain("induction step is valid");
    fireEvent.click(screen.getByRole("button", { name: "← Back to main theorem" }));
    expect(panel.textContent).toContain("By induction on");
  });

  it("shows every plan node as LLM-verified and the target PASS as the target Fact", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldSolvedModel());
    await renderWorkspace();
    fireEvent.click(screen.getByRole("tab", { name: "Attempts" }));

    const rows = planRows();
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      expect(row.textContent).toContain("LLM-verified");
    }
    expect(within(rows[2]).getByText("Target")).toBeTruthy();
    expect(screen.getByText(/became the target Fact/)).toBeTruthy();
  });
});

describe("Intermediate node attempts while the problem is still OPEN", () => {
  it("an intermediate PASS is the accepted artifact of a verified Fact, never the target", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldBlockedModel());
    await renderWorkspace();

    // Attempt 1 (lemma1 PASS) is collapsed by default — expand it.
    fireEvent.click(screen.getByRole("button", { name: /^Attempt 1\b/ }));

    expect(screen.getByText("Accepted")).toBeTruthy();
    expect(screen.getByText(/became a verified Fact/)).toBeTruthy();
    expect(screen.queryByText(/became the target Fact/)).toBeNull();
    // The accepted candidate never wears the dashed Unverified banner.
    const card = screen
      .getByRole("button", { name: /^Attempt 1\b/ })
      .closest(".attempt-card");
    expect(within(card as HTMLElement).queryByText(/Unverified — candidate proof/)).toBeNull();

    // The problem header stays OPEN — no SOLVED / LLM-verified there.
    const header = document.querySelector(".workspace-header-block") as HTMLElement;
    expect(within(header).getByText("Open")).toBeTruthy();
    expect(within(header).queryByText("LLM-verified")).toBeNull();
  });

  it("a blocked node's attempt shows the rejection with node attribution", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldBlockedModel());
    await renderWorkspace();

    // Attempt 2 (lemma2 FAIL) is the latest — expanded by default.
    expect(screen.getByText("Verification rejection")).toBeTruthy();
    expect(screen.getByText(/The triangular identity is not justified\./)).toBeTruthy();
    const attribution = screen.getByText(/Proof node:/);
    expect(attribution.textContent).toContain(LEMMA_TWO.statement.split("$")[0].trim());
  });
});

describe("Execution-level failure panel", () => {
  it("architect-invalid: panel renders with honest copy, no fake plan, no proof", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldArchitectFailureModel());
    await renderWorkspace();

    expect(screen.getByText("Invalid proof plan")).toBeTruthy();
    expect(
      screen.getByText(/dependency cycle: target depends on itself/)
    ).toBeTruthy();
    expect(screen.getByText(/failed mechanical validation/)).toBeTruthy();
    expect(screen.getByText(/No proof nodes ran\./)).toBeTruthy();
    expect(screen.getByText(/Suggested next: Retry\./)).toBeTruthy();

    // No proof structure was materialized — no plan, no Proof-tab proof.
    expect(screen.queryByText("Proof plan")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Proof" }));
    expect(screen.getByText("No verified proof yet")).toBeTruthy();
  });

  it("Retry stays a plain manual retry — wired as today, no replanning copy", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldArchitectFailureModel());
    mockedApi.startAttempt.mockResolvedValue({ status: "accepted" });
    await renderWorkspace();

    const retry = screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement;
    expect(retry.disabled).toBe(false);
    expect(document.body.textContent).not.toMatch(/replann?ing|regenerat/i);

    fireEvent.click(retry);
    await act(async () => {});
    expect(mockedApi.startAttempt).toHaveBeenCalledWith("p-1");
  });

  it("maps every outcome stage to its frozen title and retry line", () => {
    expect(
      executionFailurePanel({
        outcome_stage: "ARCHITECT_ERROR",
        error: "worker crashed",
        finished_at: null,
      })?.title
    ).toBe("Architect error");
    expect(
      executionFailurePanel({
        outcome_stage: "ARCHITECT_INVALID",
        error: "bad plan",
        finished_at: null,
      })?.title
    ).toBe("Invalid proof plan");
    for (const stage of ["SYSTEM_ERROR", "RUNTIME_ERROR"] as const) {
      expect(
        executionFailurePanel({ outcome_stage: stage, error: "boom", finished_at: null })
          ?.title
      ).toBe("Runtime error");
    }
    const interrupted = executionFailurePanel({
      outcome_stage: "INTERRUPTED",
      error: null,
      finished_at: null,
    });
    expect(interrupted?.title).toBe("Interrupted");
    expect(interrupted?.lines.join(" ")).toContain(
      "The execution ended before a final outcome was recorded."
    );
    for (const stage of [
      "ARCHITECT_ERROR",
      "ARCHITECT_INVALID",
      "SYSTEM_ERROR",
      "RUNTIME_ERROR",
      "INTERRUPTED",
    ] as const) {
      expect(
        executionFailurePanel({ outcome_stage: stage, error: "x", finished_at: null })
          ?.lines.join(" ")
      ).toContain("Suggested next: Retry.");
    }
  });
});

describe("Inspector on scaffold workspaces", () => {
  it("attempt inspector raw JSON carries the server-parsed node fields", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldBlockedModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Inspect attempt 2" }));
    const drawer = screen.getByRole("dialog");
    // jsdom does not implement summary's native toggle; set open + dispatch.
    const details = within(drawer)
      .getByText("Raw JSON")
      .closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    const raw = drawer.querySelector(".inspector-raw__pre");
    expect(raw?.textContent).toContain('"scaffold_node_id": "lemma2"');
    expect(raw?.textContent).toContain('"obligation_id": "scaffold:p-1:lemma2"');
  });

  it("fact and problem inspectors still open on scaffold workspaces", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldSolvedModel());
    await renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Inspect Main theorem" }));
    let drawer = screen.getByRole("dialog");
    expect(within(drawer).getByText("Fact")).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "Close inspector" }));

    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    drawer = screen.getByRole("dialog");
    expect(within(drawer).getByText("Problem")).toBeTruthy();
    expect(within(drawer).getByText(/no obligation yet/)).toBeTruthy();
  });

  it("lemma facts resolve by name in a scaffold proof body", async () => {
    mockedApi.getProblem.mockResolvedValue(scaffoldSolvedModel());
    await renderWorkspace();

    const refs = screen
      .getAllByRole("button", { name: "Lemma 2" })
      .filter((b) => b.closest(".proof-document") !== null);
    expect(refs.length).toBeGreaterThan(0);
    fireEvent.click(refs[0]);
    expect(screen.getByRole("button", { name: "← Back to main theorem" })).toBeTruthy();
    expect(screen.getByRole("tabpanel").textContent).toContain(SCAFFOLD_FACT_STEP.statement.split("$")[0].trim());
  });
});

describe("Legacy regression pins", () => {
  it("a legacy workspace shows no proof plan and no execution failure panel", async () => {
    const { openRejectionModel } = await import("../test-support/workspaceFixtures");
    mockedApi.getProblem.mockResolvedValue(openRejectionModel());
    await renderWorkspace();

    expect(screen.queryByText("Proof plan")).toBeNull();
    expect(screen.queryByText(/No proof nodes ran\./)).toBeNull();
    // Legacy LEMMA_ONE copy untouched by scaffold node attribution.
    expect(screen.queryByText(/Proof node:/)).toBeNull();
    expect(LEMMA_ONE.fact_id).toBeTruthy();
  });
});
