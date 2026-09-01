/**
 * Typed REST client — the ONLY module that knows HTTP (spec §10).
 * Everything else consumes the contract types from ../types.
 */

import type {
  ArchiveProblemResponse,
  CreateProblemResponse,
  ForkProblemResponse,
  ProblemListResponse,
  StartAttemptResponse,
  WorkspaceReadModel,
} from "../types";

export class ApiError extends Error {
  /** HTTP status, or null when the request never reached the server. */
  readonly status: number | null;
  /** Machine-readable code from an `{"error": "…"}` body (e.g.
   *  `already_running`, `already_solved`), or null when absent. */
  readonly code: string | null;

  constructor(status: number | null, message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      null,
      "Could not reach the Noespire server. Check that it is running and try again."
    );
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const code =
      typeof body === "object" && body !== null && "error" in body && typeof body.error === "string"
        ? body.error
        : null;
    const message =
      code ||
      (typeof body === "object" && body !== null &&
        "detail" in body && typeof body.detail === "string" && body.detail) ||
      `Request failed with status ${response.status}.`;
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}

export function listProblems(): Promise<ProblemListResponse> {
  return request<ProblemListResponse>("/api/problems");
}

export function createProblem(statement: string): Promise<CreateProblemResponse> {
  return request<CreateProblemResponse>("/api/problems", {
    method: "POST",
    body: JSON.stringify({ statement }),
  });
}

export function getProblem(problemId: string): Promise<WorkspaceReadModel> {
  return request<WorkspaceReadModel>(
    `/api/problems/${encodeURIComponent(problemId)}`
  );
}

/**
 * POST /api/problems/{id}/attempts (spec §6). 202 on success; failure modes
 * are distinguishable via ApiError: 409 + code "already_running" /
 * "already_solved", 404 unknown id. Retry is deliberately not its own verb.
 */
export function startAttempt(problemId: string): Promise<StartAttemptResponse> {
  return request<StartAttemptResponse>(
    `/api/problems/${encodeURIComponent(problemId)}/attempts`,
    { method: "POST" }
  );
}

/**
 * POST /api/problems/{id}/fork (spec §6). 201 with the created child;
 * 400 blank statement, 404 unknown parent. The parent is never modified.
 */
export function forkProblem(
  problemId: string,
  statement: string
): Promise<ForkProblemResponse> {
  return request<ForkProblemResponse>(
    `/api/problems/${encodeURIComponent(problemId)}/fork`,
    { method: "POST", body: JSON.stringify({ statement }) }
  );
}

/**
 * POST /api/problems/{id}/archive (spec §6). 200 `{ archived }`; metadata-only,
 * idempotent; 404 unknown id.
 */
export function setProblemArchived(
  problemId: string,
  archived: boolean
): Promise<ArchiveProblemResponse> {
  return request<ArchiveProblemResponse>(
    `/api/problems/${encodeURIComponent(problemId)}/archive`,
    { method: "POST", body: JSON.stringify({ archived }) }
  );
}
