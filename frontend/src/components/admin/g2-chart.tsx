"use client";

import * as React from "react";
import { useTheme } from "next-themes";

/**
 * Thin React wrapper around AntV G2 v5 (spec/options API).
 * Usage: <G2Chart height={260} options={{ type: "interval", data, encode: { x: "date", y: "n" } }} />
 * G2 is imported dynamically so it never runs during SSR.
 */
export function G2Chart({ options, height = 260 }: { options: Record<string, unknown>; height?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  React.useEffect(() => {
    let chart: { destroy: () => void } | undefined;
    let cancelled = false;
    (async () => {
      const { Chart } = await import("@antv/g2");
      if (cancelled || !ref.current) return;
      const c = new Chart({ container: ref.current, autoFit: true, height });
      c.options({
        theme: resolvedTheme === "dark" ? "classicDark" : "classic",
        ...options,
        style: { ...(options.style as object) },
      } as Parameters<typeof c.options>[0]);
      c.render();
      chart = c;
    })();
    return () => {
      cancelled = true;
      chart?.destroy();
    };
  }, [options, height, resolvedTheme]);

  return <div ref={ref} style={{ height }} className="w-full" dir="ltr" />;
}
