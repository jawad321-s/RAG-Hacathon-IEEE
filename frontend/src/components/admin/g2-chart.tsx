"use client";

import * as React from "react";

/**
 * Thin React wrapper around AntV G2 v5 (spec/options API).
 * Usage: <G2Chart height={260} options={{ type: "interval", data, encode: { x: "date", y: "n" } }} />
 * G2 is imported dynamically so it never runs during SSR.
 */
const FONT = "IBM Plex Sans Arabic, Helvetica Neue, Arial, sans-serif";

export function G2Chart({ options, height = 260 }: { options: Record<string, unknown>; height?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let chart: { destroy: () => void } | undefined;
    let cancelled = false;
    (async () => {
      const { Chart } = await import("@antv/g2");
      if (cancelled || !ref.current) return;
      const c = new Chart({ container: ref.current, autoFit: true, height });
      c.options({
        theme: "classic",
        axis: { x: { labelFontFamily: FONT, titleFontFamily: FONT }, y: { labelFontFamily: FONT, titleFontFamily: FONT } },
        legend: { color: { itemLabelFontFamily: FONT } },
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
  }, [options, height]);

  return <div ref={ref} style={{ height }} className="w-full" dir="ltr" />;
}
