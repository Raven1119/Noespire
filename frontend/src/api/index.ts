/**
 * Typed REST client — the ONLY module that knows HTTP (spec §10).
 * Everything else consumes the contract types from ../types.
 */

import type {
  CreateProblemResponse,
  ProblemListResponse,
  WorkspaceReadModel,
} from "../types";

export class ApiError extends Error {
  /** HTTP status, or null when the request never reached the server. */
  readonly status: number | null;

  constructor(status: number | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
    const message =
      (typeof body === "object" && body !== null &&
        (("error" in body && typeof body.error === "string" && body.error) ||
          ("detail" in body && typeof body.detail === "string" && body.detail))) ||
      `Request failed with status ${response.status}.`;
    throw new ApiError(response.status, message);
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
