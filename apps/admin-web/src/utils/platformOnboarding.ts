import { ApiError } from "../api/client";
import type { PlatformOnboardingSession } from "../api/types";

export const ONBOARDING_CONFIRM_TIMEOUT_CODE = "ONBOARDING_CONFIRM_TIMEOUT";
export const ONBOARDING_CONFIRM_UNCERTAIN_CODE = "ONBOARDING_CONFIRM_UNCERTAIN";
export const ONBOARDING_CONFIRM_RESULT_INCOMPLETE_CODE =
  "ONBOARDING_CONFIRM_RESULT_INCOMPLETE";

const DEFAULT_CONFIRM_TIMEOUT_MS = 20_000;
const DEFAULT_RECOVERY_TIMEOUT_MS = 8_000;

type ConfirmationRecoveryOptions = {
  confirm: () => Promise<PlatformOnboardingSession>;
  reload: () => Promise<PlatformOnboardingSession>;
  confirmTimeoutMs?: number;
  recoveryTimeoutMs?: number;
};

type DeliveryUrlOptions = {
  origin?: string;
  adminBasePath?: string;
  publicCardBaseUrl?: string;
};

function isCompleteConfirmation(
  session: PlatformOnboardingSession,
): boolean {
  return session.status === "confirmed" && Boolean(session.confirmedEnterprise);
}

function timeoutError(message: string, code: string): ApiError {
  return new ApiError(message, { code });
}

async function within<T>(
  promise: Promise<T>,
  timeoutMs: number,
  createError: () => ApiError,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(createError()), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

function mayHaveCommitted(error: unknown): boolean {
  if (error instanceof ApiError) {
    return (
      error.status === undefined ||
      error.status >= 500 ||
      error.code === "NETWORK_ERROR" ||
      error.code === ONBOARDING_CONFIRM_TIMEOUT_CODE ||
      error.code === ONBOARDING_CONFIRM_RESULT_INCOMPLETE_CODE
    );
  }
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Confirmation is an idempotent server operation, but a slow or interrupted
 * connection can hide a successful commit from the browser. Bound the waiting
 * state and reconcile the authoritative session before reporting failure.
 */
export async function confirmOnboardingWithRecovery({
  confirm,
  reload,
  confirmTimeoutMs = DEFAULT_CONFIRM_TIMEOUT_MS,
  recoveryTimeoutMs = DEFAULT_RECOVERY_TIMEOUT_MS,
}: ConfirmationRecoveryOptions): Promise<PlatformOnboardingSession> {
  let originalError: unknown;
  try {
    const confirmed = await within(
      confirm(),
      confirmTimeoutMs,
      () =>
        timeoutError(
          "企业确认等待超时，正在核对服务端是否已经完成开通。",
          ONBOARDING_CONFIRM_TIMEOUT_CODE,
        ),
    );
    if (isCompleteConfirmation(confirmed)) return confirmed;
    originalError = timeoutError(
      "服务端没有返回完整的企业交付结果，正在重新核对。",
      ONBOARDING_CONFIRM_RESULT_INCOMPLETE_CODE,
    );
  } catch (error) {
    if (!mayHaveCommitted(error)) throw error;
    originalError = error;
  }

  try {
    const recovered = await within(
      reload(),
      recoveryTimeoutMs,
      () =>
        timeoutError(
          "暂时无法核对企业开通结果，请稍后点击“核对开通结果”。",
          ONBOARDING_CONFIRM_UNCERTAIN_CODE,
        ),
    );
    if (isCompleteConfirmation(recovered)) return recovered;
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.code === ONBOARDING_CONFIRM_UNCERTAIN_CODE
    ) {
      throw error;
    }
  }

  throw new ApiError(
    "当前无法确认企业是否已开通。请勿重复填写，点击“核对开通结果”从服务端重新加载。",
    {
      code: ONBOARDING_CONFIRM_UNCERTAIN_CODE,
      requestId:
        originalError instanceof ApiError ? originalError.requestId : undefined,
    },
  );
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}

/** Builds stable delivery URLs from the deployed admin base (`/c/admin/`). */
export function buildOnboardingDeliveryUrls(
  cardSlug: string,
  options: DeliveryUrlOptions = {},
): { cardUrl: string; adminUrl: string } {
  const origin = options.origin ?? globalThis.location?.origin ?? "http://localhost";
  const adminBasePath = options.adminBasePath ?? import.meta.env.BASE_URL;
  const adminUrl = new URL(ensureTrailingSlash(adminBasePath), origin);

  let cardBase: URL;
  if (options.publicCardBaseUrl?.trim()) {
    cardBase = new URL(ensureTrailingSlash(options.publicCardBaseUrl.trim()), origin);
  } else if (adminUrl.pathname.endsWith("/admin/")) {
    cardBase = new URL(
      adminUrl.pathname.slice(0, -"admin/".length),
      adminUrl.origin,
    );
  } else {
    cardBase = new URL("/c/", adminUrl.origin);
  }

  return {
    cardUrl: new URL(encodeURIComponent(cardSlug), ensureTrailingSlash(cardBase.href)).href,
    adminUrl: adminUrl.href,
  };
}
