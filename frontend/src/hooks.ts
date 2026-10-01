import { useCallback, useEffect, useState } from "react";
import { api } from "./lib";
export function useResource<T>(path: string) {
  const [result, setResult] = useState<{ path: string; data: T } | null>(null),
    [error, setError] = useState(""),
    [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let live = true;
    api<T>(path)
      .then((d) => {
        if (live) {
          setResult({ path, data: d });
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [path, version]);
  return { data: result?.path === path ? result.data : null, error, refresh };
}
