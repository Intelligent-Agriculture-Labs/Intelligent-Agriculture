"""Soil texture classification (USDA triangle, simplified) and available water capacity.

Total available water per metre of root zone (TAW = 1000·(θFC − θWP)) follows FAO-56 Table 19 ranges
(mid-points), e.g. sand 55, loamy sand 80, sandy loam 110, loam 145, silt loam 165, clay loam 160, clay 150 mm/m.
"""

from __future__ import annotations

TAW_MM_PER_M = {
    "sand": 55.0,
    "loamy sand": 80.0,
    "sandy loam": 110.0,
    "loam": 145.0,
    "silt loam": 165.0,
    "silt": 170.0,
    "sandy clay loam": 125.0,
    "clay loam": 160.0,
    "silty clay loam": 165.0,
    "sandy clay": 130.0,
    "silty clay": 155.0,
    "clay": 150.0,
}

# readily-evaporable water REW [mm] and TEW for a 0.1 m evaporation layer (FAO-56 Table 19 mid-points)
REW_MM = {"sand": 4, "loamy sand": 6, "sandy loam": 8, "loam": 9, "silt loam": 10, "silt": 10}


def texture_class(sand: float, clay: float) -> str:
    """USDA texture class from sand/clay % (silt = remainder)."""
    silt = 100 - sand - clay
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 1.5 * clay < 30:
        return "loamy sand"
    if clay >= 40:
        if silt >= 40:
            return "silty clay"
        if sand > 45:
            return "sandy clay"
        return "clay"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 27:
        if sand <= 20:
            return "silty clay loam"
        if sand <= 45:
            return "clay loam"
        return "sandy clay loam"
    if clay >= 20 and sand > 45 and silt < 28:
        return "sandy clay loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if silt >= 50:
        return "silt loam"
    if clay >= 7 and silt >= 28 and sand <= 52:
        return "loam"
    return "sandy loam"


def taw_mm_per_m(texture: str) -> float:
    return TAW_MM_PER_M.get(texture, 140.0)


def rew_mm(texture: str) -> float:
    return float(REW_MM.get(texture, 9))
