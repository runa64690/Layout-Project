"""Convex geometry in cell units; clockwise rotation uses fractional quarter turns."""
import math

EPSILON = 1e-6


def rect_polygon(rect):
    x0, y0, x1, y1 = rect
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rotated_size(width, depth, rotation):
    angle = rotation * math.pi / 2
    c, s = abs(math.cos(angle)), abs(math.sin(angle))
    return width * c + depth * s, width * s + depth * c


def transform_polygon(points, center, rotation):
    angle = rotation * math.pi / 2
    c, s = math.cos(angle), math.sin(angle)
    return [(center[0] + c*x + s*y, center[1] - s*x + c*y) for x, y in points]


def bounds(points):
    return (min(x for x, y in points), min(y for x, y in points),
            max(x for x, y in points), max(y for x, y in points))


def _cross(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])


def intersection_polygon(subject, clip):
    """Sutherland-Hodgman clipping for counterclockwise convex polygons."""
    result = list(subject)
    for a, b in zip(clip, clip[1:] + clip[:1]):
        source, result = result, []
        if not source:
            break
        previous = source[-1]
        d0 = _cross(a, b, previous)
        for current in source:
            d1 = _cross(a, b, current)
            if (d0 >= 0) != (d1 >= 0):
                t = d0 / (d0 - d1)
                result.append((previous[0] + t*(current[0]-previous[0]),
                               previous[1] + t*(current[1]-previous[1])))
            if d1 >= 0:
                result.append(current)
            previous, d0 = current, d1
    return result


def polygon_area(points):
    return abs(sum(a[0]*b[1] - b[0]*a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2


def intersection_area(a, b):
    return polygon_area(intersection_polygon(a, b))


def overlaps(a, b):
    """Separating axis test, with touching edges allowed (same tolerance as Unity)."""
    for polygon in (a, b):
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            nx, ny = -(q[1]-p[1]), q[0]-p[0]
            length = math.hypot(nx, ny)
            if length == 0:
                continue
            pa = [(x*nx+y*ny)/length for x, y in a]
            pb = [(x*nx+y*ny)/length for x, y in b]
            if min(max(pa), max(pb)) - max(min(pa), min(pb)) <= EPSILON:
                return False
    return True


def occupied_cells(polygon):
    x0, y0, x1, y1 = bounds(polygon)
    for x in range(math.floor(x0), math.ceil(x1)):
        for y in range(math.floor(y0), math.ceil(y1)):
            if overlaps(polygon, rect_polygon((x, y, x+1, y+1))):
                yield x, y
