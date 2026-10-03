#!/usr/bin/env python3
"""Compress one reconstructed OpenFOAM frame inside WSL."""
import argparse
import array
import os
import re
import struct
import sys


def parse_field(path, components, expected_count=None):
    data = open(path, "rb").read()
    start = data.find(b"internalField")
    if start < 0:
        raise ValueError("internalField not found: " + path)
    match = re.search(rb"List<(?:scalar|vector)>\s*\n(\d+)\s*\n\(", data[start:start + 240])
    if not match:
        uniform = re.search(rb"internalField\s+uniform\s+(\([^)]*\)|[-+0-9.eE]+)\s*;",
                            data[start:start + 512])
        if not uniform or not expected_count:
            raise ValueError("binary/uniform field data not found: " + path)
        raw = uniform.group(1).strip().strip(b"()")
        numbers = [float(value) for value in raw.split()]
        if len(numbers) != components:
            raise ValueError("uniform field component mismatch: " + path)
        values = array.array("d", numbers * expected_count)
        return expected_count, values
    count = int(match.group(1))
    offset = start + match.start() + len(match.group(0))
    values = array.array("d")
    values.frombytes(data[offset:offset + count * 8 * components])
    if len(values) != count * components:
        raise ValueError("truncated field: " + path)
    return count, values


def atomic_write(path, chunks):
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as stream:
            for chunk in chunks:
                stream.write(chunk)
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def prepare_grid(c_path):
    count, centres = parse_field(c_path, 3)
    xs, ys, zs = centres[0::3], centres[1::3], centres[2::3]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    z0, z1 = min(zs), max(zs)
    nx = max(2, round((x1 - x0) / 0.01))
    ny = max(2, round((y1 - y0) / 0.01))
    # Limit axial display bins to source layers to avoid artificial empty slabs
    z_layers = sorted({round(value, 10) for value in zs})
    nominal_nz = max(2, round((z1 - z0) / 0.01))
    use_source_layers = len(z_layers) <= nominal_nz
    nz = max(2, len(z_layers)) if use_source_layers else nominal_nz
    z_layer_index = {value: index for index, value in enumerate(z_layers)} if use_source_layers else None
    fx = nx / (x1 - x0 + 1e-12)
    fy = ny / (y1 - y0 + 1e-12)
    fz = nz / (z1 - z0 + 1e-12)
    indexes = array.array("i", bytes(4 * count))
    occupancy = bytearray(nx * ny * nz)
    for i in range(count):
        ix = min(nx - 1, int((xs[i] - x0) * fx))
        iy = min(ny - 1, int((ys[i] - y0) * fy))
        iz = (z_layer_index[round(zs[i], 10)] if z_layer_index is not None
              else min(nz - 1, int((zs[i] - z0) * fz)))
        indexes[i] = (iz * ny + iy) * nx + ix
        occupancy[indexes[i]] = 255
    return {"count": count, "indexes": indexes, "occupancy": occupancy,
            "nx": nx, "ny": ny, "nz": nz, "bbox": (x0, y0, z0, x1, y1, z1)}


def header(magic, grid):
    return (magic + struct.pack("<3I", grid["nx"], grid["ny"], grid["nz"])
            + struct.pack("<6f", *grid["bbox"]))


def compress_bubbles(source, target, grid, threshold=0.03):
    count, values = parse_field(source, 1, grid["count"])
    selected = [(i, values[i]) for i in range(count) if values[i] > threshold]
    chunks = [b"BUB1" + struct.pack("<2I", len(selected), count)]
    chunks.extend(struct.pack("<If", i, value) for i, value in selected)
    atomic_write(target, chunks)


def compress_flow(source, target, grid):
    count, values = parse_field(source, 3, grid["count"])
    if count != grid["count"]:
        raise ValueError("U/C cell count mismatch")
    bins = grid["nx"] * grid["ny"] * grid["nz"]
    sums = array.array("d", bytes(8 * bins * 3))
    hits = array.array("i", bytes(4 * bins))
    for i in range(count):
        b = grid["indexes"][i]
        b3, i3 = b * 3, i * 3
        sums[b3] += values[i3]
        sums[b3 + 1] += values[i3 + 1]
        sums[b3 + 2] += values[i3 + 2]
        hits[b] += 1
    result = array.array("f", bytes(4 * bins * 3))
    for b in range(bins):
        if hits[b]:
            b3 = b * 3
            result[b3] = sums[b3] / hits[b]
            result[b3 + 1] = sums[b3 + 1] / hits[b]
            result[b3 + 2] = sums[b3 + 2] / hits[b]
    atomic_write(target, (header(b"FLW1", grid), result.tobytes()))


def compress_temperature(source, target, grid):
    count, values = parse_field(source, 1, grid["count"])
    if count != grid["count"]:
        raise ValueError("T/C cell count mismatch")
    bins = grid["nx"] * grid["ny"] * grid["nz"]
    sums = array.array("d", bytes(8 * bins))
    hits = array.array("i", bytes(4 * bins))
    for i in range(count):
        b = grid["indexes"][i]
        sums[b] += values[i]
        hits[b] += 1
    result = array.array("f", bytes(4 * bins))
    for b in range(bins):
        if hits[b]:
            result[b] = sums[b] / hits[b]
    atomic_write(target, (header(b"THM1", grid), result.tobytes()))


def averaged_scalar(source, grid):
    """Average one OpenFOAM cell scalar onto the viewer's regular grid."""
    count, values = parse_field(source, 1, grid["count"])
    if count != grid["count"]:
        raise ValueError("scalar/C cell count mismatch")
    bins = grid["nx"] * grid["ny"] * grid["nz"]
    sums = array.array("d", bytes(8 * bins))
    hits = array.array("i", bytes(4 * bins))
    for i in range(count):
        b = grid["indexes"][i]
        sums[b] += values[i]
        hits[b] += 1
    result = array.array("f", bytes(4 * bins))
    for b in range(bins):
        if hits[b]:
            result[b] = sums[b] / hits[b]
    return result


def compress_scalar(source, target, grid, magic):
    result = averaged_scalar(source, grid)
    atomic_write(target, (header(magic, grid), result.tobytes()))


def compress_turbulence(k_path, epsilon_path, target, grid):
    kval = averaged_scalar(k_path, grid)
    epsilon = averaged_scalar(epsilon_path, grid)
    atomic_write(target, (header(b"TRB1", grid), kval.tobytes(), epsilon.tobytes()))


def compress_phase(water_path, vapour_path, target, grid):
    water_count, water = parse_field(water_path, 1, grid["count"])
    vapour_count, vapour = parse_field(vapour_path, 1, grid["count"])
    if water_count != grid["count"] or vapour_count != grid["count"]:
        raise ValueError("phase/C cell count mismatch")
    bins = grid["nx"] * grid["ny"] * grid["nz"]
    water_sums = array.array("d", bytes(8 * bins))
    vapour_sums = array.array("d", bytes(8 * bins))
    hits = array.array("i", bytes(4 * bins))
    for i in range(water_count):
        b = grid["indexes"][i]
        water_sums[b] += water[i]
        vapour_sums[b] += vapour[i]
        hits[b] += 1
    water_out, vapour_out = bytearray(bins), bytearray(bins)
    for b in range(bins):
        if hits[b]:
            w = max(0.0, min(1.0, water_sums[b] / hits[b]))
            v = max(0.0, min(1.0, vapour_sums[b] / hits[b]))
            water_out[b] = int(w * 255.0 + 0.5)
            vapour_out[b] = int(v * 255.0 + 0.5)
    atomic_write(target, (header(b"PHS2", grid), water_out, vapour_out, grid["occupancy"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--centres", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--alpha")
    parser.add_argument("--water")
    parser.add_argument("--flow")
    parser.add_argument("--temperature")
    parser.add_argument("--pressure")
    parser.add_argument("--k")
    parser.add_argument("--epsilon")
    parser.add_argument("--bubble", action="store_true")
    parser.add_argument("--phase", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+(?:\.\d+)?", args.time):
        raise ValueError("invalid simulation time")
    os.makedirs(args.out, exist_ok=True)
    grid = prepare_grid(args.centres)
    if args.bubble:
        compress_bubbles(args.alpha, os.path.join(args.out, "bub_" + args.time + ".bin"), grid)
    if args.flow:
        compress_flow(args.flow, os.path.join(args.out, "flow_" + args.time + ".bin"), grid)
    if args.temperature:
        compress_temperature(args.temperature, os.path.join(args.out, "therm_" + args.time + ".bin"), grid)
    if args.pressure:
        compress_scalar(args.pressure, os.path.join(args.out, "pressure_" + args.time + ".bin"),
                        grid, b"PRS1")
    if args.k or args.epsilon:
        if not (args.k and args.epsilon):
            raise ValueError("turbulence output requires both k and epsilon")
        compress_turbulence(args.k, args.epsilon,
                            os.path.join(args.out, "turbulence_" + args.time + ".bin"), grid)
    if args.phase:
        if args.water and os.path.isfile(args.water):
            compress_phase(args.water, args.alpha, os.path.join(args.out, "phase_" + args.time + ".bin"), grid)
        else:
            atomic_write(os.path.join(args.out, ".no_phase_" + args.time), ())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("wsl_frame_compress: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
