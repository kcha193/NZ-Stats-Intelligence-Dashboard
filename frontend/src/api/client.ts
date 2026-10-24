import { ApiError } from "./errors";
import { isStaticMode } from "./mode";
import { staticGetJson } from "./static";

export { ApiError };

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (isStaticMode()) return staticGetJson<T>(path, signal);
  const res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body: keep the status text */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}
