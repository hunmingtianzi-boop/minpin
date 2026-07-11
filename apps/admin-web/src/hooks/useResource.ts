import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export type ResourceStatus =
  | "loading"
  | "ready"
  | "empty"
  | "error"
  | "permission";

export type ResourceState<T> = {
  status: ResourceStatus;
  data?: T;
  error?: ApiError;
  reload: () => void;
};

function isEmpty(value: unknown): boolean {
  return value === null || (Array.isArray(value) && value.length === 0);
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError("加载数据时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function useResource<T>(
  loader: () => Promise<T>,
  dependencyKey?: string | number | boolean,
): ResourceState<T> {
  const loaderRef = useRef(loader);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<Omit<ResourceState<T>, "reload">>({
    status: "loading",
  });

  loaderRef.current = loader;

  const reload = useCallback(() => {
    setReloadKey((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });

    void loaderRef.current().then(
      (data) => {
        if (!active) return;
        setState({ status: isEmpty(data) ? "empty" : "ready", data });
      },
      (error: unknown) => {
        if (!active) return;
        const apiError = asApiError(error);
        setState({
          status: apiError.status === 403 ? "permission" : "error",
          error: apiError,
        });
      },
    );

    return () => {
      active = false;
    };
  }, [dependencyKey, reloadKey]);

  return { ...state, reload };
}
