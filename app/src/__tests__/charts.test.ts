import { niceTicks } from "@/components/charts";

describe("niceTicks", () => {
  it.each([
    [0, 252],
    [0, 7.9],
    [-1.3, 2.2],
    [13, 31],
    [0.11, 0.19],
  ])("covers the full data range %p..%p", (lo, hi) => {
    const t = niceTicks(lo, hi);
    expect(t[0]).toBeLessThanOrEqual(lo);
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(hi);
    expect(t.length).toBeGreaterThanOrEqual(2);
    expect(t.length).toBeLessThanOrEqual(7);
  });
});
