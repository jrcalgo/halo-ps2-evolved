"""Exercise CE's real wind selection/update/current path from a raw retail map."""
from pathlib import Path
import hashlib
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
WIND_BLOCK_OFFSET = 436
WIND_PALETTE_STRIDE = 0xF0
CLUSTER_BLOCK_OFFSET = 308
CLUSTER_STRIDE = 0x68
WIND_REFERENCE_INDEX_OFFSET = 0x8C
WIND_DIRECTION_OFFSET = 0x90
WIND_MAGNITUDE_OFFSET = 0x9C
WIND_DEFINITION_BYTES = 0x40
LOCAL_SEED = 0x89ABCDEF

sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from halo_random_directions import direction_table  # noqa: E402


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _c_float(value):
    text = f"{value:.9g}"
    if "." not in text and "e" not in text.lower():
        text += ".0"
    return text + "f"


def _raw_wind_oracle(map_path):
    """Read source BSP/tag bytes, not the package, as the expected inputs."""
    index = tagindex.TagIndex.read(map_path)
    tag_region, tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(map_path).decompressed_size)
    index_by_datum = {entry.tag_id: entry for entry in index.entries}
    chosen = None
    palette_rows = None
    for bsp_index, location in enumerate(locations):
        with Path(map_path).open("rb") as stream:
            stream.seek(location.file_offset)
            image = stream.read(location.size)
        if len(image) != location.size:
            raise AssertionError(f"truncated retail BSP {location.path}")
        root = struct.unpack_from("<I", image, 0)[0] - location.address
        if root < 0 or root + 648 > len(image):
            raise AssertionError(f"retail BSP root leaves {location.path}")

        palette_count, palette_address = struct.unpack_from(
            "<iI", image, root + WIND_BLOCK_OFFSET)
        palette_offset = palette_address - location.address
        if (palette_count < 0 or palette_offset < 0 or
                palette_offset + palette_count * WIND_PALETTE_STRIDE > len(image)):
            raise AssertionError(f"weather-palette extent leaves {location.path}")
        cluster_count, cluster_address = struct.unpack_from(
            "<iI", image, root + CLUSTER_BLOCK_OFFSET)
        cluster_offset = cluster_address - location.address
        if (cluster_count < 0 or cluster_offset < 0 or
                cluster_offset + cluster_count * CLUSTER_STRIDE > len(image)):
            raise AssertionError(f"cluster extent leaves {location.path}")

        rows = []
        for palette_index in range(palette_count):
            entry = palette_offset + palette_index * WIND_PALETTE_STRIDE
            datum = struct.unpack_from(
                "<I", image, entry + WIND_REFERENCE_INDEX_OFFSET)[0]
            direction = struct.unpack_from(
                "<3f", image, entry + WIND_DIRECTION_OFFSET)
            magnitude = struct.unpack_from(
                "<f", image, entry + WIND_MAGNITUDE_OFFSET)[0]
            if datum == 0xFFFFFFFF:
                rows.append({"datum": datum, "direction": direction,
                             "magnitude": magnitude, "definition": (0.0,) * 7})
                continue
            tag = index_by_datum.get(datum)
            if tag is None or tag.group != "wind":
                raise AssertionError(
                    f"weather palette datum {datum:#010x} is not a wind tag")
            tag_offset = tag.data_address - tag_base
            if (tag_offset < 0 or
                    tag_offset + WIND_DEFINITION_BYTES > len(tag_region)):
                raise AssertionError(f"wind tag data leaves raw tag region: {tag.path}")
            definition = struct.unpack_from("<7f", tag_region, tag_offset)
            rows.append({"datum": datum, "direction": direction,
                         "magnitude": magnitude, "definition": definition,
                         "tag_path": tag.path})

        for cluster_index in range(cluster_count):
            cluster = cluster_offset + cluster_index * CLUSTER_STRIDE
            fog_reference = struct.unpack_from("<h", image, cluster + 2)[0]
            weather_index = struct.unpack_from("<h", image, cluster + 8)[0]
            if (fog_reference == -1 and 0 <= weather_index < palette_count and
                    weather_index == 0 and
                    rows[weather_index]["datum"] != 0xFFFFFFFF):
                chosen = {"bsp_index": bsp_index, "bsp_path": location.path,
                          "cluster_index": cluster_index,
                          "fog_reference": fog_reference,
                          "weather_index": weather_index,
                          "weather_count": palette_count,
                          "cluster_count": cluster_count}
                palette_rows = rows
                break
        if chosen:
            break
    if chosen is None:
        raise AssertionError("no retail cluster has fog NONE and a valid windy palette")
    chosen["palette"] = palette_rows
    return chosen


def _expected_vectors(raw, global_seed, local_seed):
    """Independent f32 model, using the offline CE geosphere table generator."""
    directions = direction_table()

    def next_seed(seed):
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        return seed, seed >> 16

    def random_range(seed, lower, upper):
        seed, value = next_seed(seed)
        return seed, lower + (((upper - lower) * value) >> 16)

    # random_math_initialize builds the lookup from geosphere_new(16); CE then
    # consumes 24 global-seed table indices in control-point/axis order.
    variance = [[[0.0, 0.0, 0.0] for _ in range(64)] for _ in range(3)]
    seed = global_seed
    for control in range(8):
        for axis in range(3):
            seed, random16 = next_seed(seed)
            # seed_random_direction3d uses real_seed_random_range (top 16
            # bits divided by 65535), then truncates the scaled real to short.
            direction_sample = _f32(random16 / 65535.0)
            index = int(_f32(len(directions) * direction_sample))
            variance[axis][control * 8] = tuple(_f32(c) for c in directions[index])

    def spline(f0, f1, f2, f3, t0, h, t):
        f3, f2, f1 = _f32(f3 - f2), _f32(f2 - f1), _f32(f1 - f0)
        f3, f2 = _f32(f3 - f2), _f32(f2 - f1)
        inner = _f32(f2 + _f32(_f32(t - (t0 + 2.0 * h)) *
                               _f32(_f32(f3 - f2) / _f32(3.0 * h))))
        inner = _f32(f1 + _f32(_f32(t - (t0 + h)) * _f32(inner / _f32(2.0 * h))))
        return _f32(f0 + _f32(_f32((t - t0) / h) * inner))

    for control in range(8):
        controls = ((control - 1) & 7, control, (control + 1) & 7,
                    (control + 2) & 7)
        for sample in range(1, 8):
            t = _f32(sample * 0.125 + control)
            for axis in range(3):
                for component in range(3):
                    values = [variance[axis][item * 8][component]
                              for item in controls]
                    variance[axis][control * 8 + sample][component] = spline(
                        *values, float(controls[1] - 1), 1.0, t)

    states = []
    seed = local_seed
    for row in raw["palette"]:
        if row["datum"] == 0xFFFFFFFF:
            states.append(None)
            continue
        # wind_definition embeds real_euler_angles2d in its declared {yaw,
        # pitch} order. Keep the independent source-data model aligned with
        # those CE fields; the third raw float is yaw variation, the fourth
        # is pitch variation.
        lower, upper, yaw_area, pitch_area, local_weight, rate, damping = row["definition"]
        del rate
        changes = []
        for _ in range(3):
            seed, sample = random_range(seed, 0, 2)
            changes.append(0.01 if sample else -0.01)
        velocity_variance = max(0.0, _f32(changes[0]))
        pitch_variance = _f32(changes[1])
        yaw_variance = _f32(changes[2])
        velocity = _f32(_f32(_f32(upper - lower) * velocity_variance) + lower)

        x, y, z = row["direction"]
        yaw = _f32(math.atan2(y, x))
        pitch = _f32(math.atan2(z, math.sqrt(x * x + y * y)))
        pitch = _f32(pitch + _f32(_f32(pitch_area * pitch_variance) * 0.5))
        yaw = _f32(yaw + _f32(_f32(yaw_area * yaw_variance) * 0.5))
        cosine_pitch = _f32(math.cos(pitch))
        vector = (_f32(_f32(math.cos(yaw)) * cosine_pitch),
                  _f32(_f32(math.sin(yaw)) * cosine_pitch),
                  _f32(math.sin(pitch)))
        scale = _f32(row["magnitude"] * velocity)
        states.append({"velocity": velocity,
                       "velocity3d": tuple(_f32(component * scale)
                                           for component in vector),
                       "weight": local_weight, "rate": row["definition"][5],
                       "damping": damping})

    # The query fixture uses position=(0,0,0) and performs exactly one update.
    def bitcast_float(value):
        return struct.unpack("<I", struct.pack("<f", value))[0]

    def local_variance(state):
        magnitude = _f32(_f32(state["weight"] * state["velocity"]) / 3.0)
        total = [0.0, 0.0, 0.0]
        for axis, axis_scale in enumerate((0.1, 0.2, 0.07)):
            key = _f32(_f32(_f32(axis_scale * 1.0) * state["rate"]) * 8.0)
            bits = bitcast_float(key) & 0x7FFFFFFF
            adjusted = _f32(struct.unpack("<f", struct.pack("<I", bits))[0] + 8388608.0)
            sample_index = (bitcast_float(adjusted) & 0xFF) & 0x3F
            for component in range(3):
                total[component] = _f32(total[component] +
                                        variance[axis][sample_index][component])
        return tuple(_f32(component * magnitude) for component in total)

    result = {}
    for index, state in enumerate(states):
        if state is None:
            continue
        local = local_variance(state)
        base = state["velocity3d"]
        result[index, "normal"] = tuple(
            _f32(_f32(component * _f32(1.0 - state["weight"])) + extra)
            for component, extra in zip(base, local))
        result[index, "simple"] = tuple(
            _f32(component + extra) for component, extra in zip(base, local))
        result[index, "damped"] = tuple(
            _f32(component * _f32(1.0 - state["damping"]))
            for component in result[index, "normal"])
    return result


class HcuWindConsumerTest(unittest.TestCase):
    def test_raw_retail_weather_palette_drives_ce_wind_update_and_query(self):
        map_path = ROOT / "build/retail-maps/decompressed/a30.map"
        if not map_path.is_file():
            self.skipTest(f"decompressed retail map is missing: {map_path}")
        source_sha256 = hashlib.sha256(map_path.read_bytes()).hexdigest()
        self.assertEqual(source_sha256,
                         "287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293")
        raw = _raw_wind_oracle(map_path)
        self.assertEqual((raw["bsp_index"], raw["cluster_index"],
                          raw["weather_index"], raw["fog_reference"]),
                         (0, 33, 0, -1))
        self.assertEqual(raw["bsp_path"], r"levels\a30\a30_a")

        expected = _expected_vectors(raw, 0x13579BDF, LOCAL_SEED)
        geosphere_directions = direction_table()
        with tempfile.TemporaryDirectory(prefix="hcu-wind-") as temp_name:
            temp = Path(temp_name)
            header = temp / "hcu_wind_raw_fixture.h"
            rows = raw["palette"]
            lines = [
                f"#define HCU_WIND_PALETTE_COUNT {len(rows)}",
                f"#define HCU_WIND_CLUSTER_COUNT {raw['cluster_count']}",
                f"#define HCU_WIND_SELECTED_CLUSTER {raw['cluster_index']}",
                f"#define HCU_WIND_SELECTED_PALETTE {raw['weather_index']}",
                "static const float HCU_GEOSPHERE_DIRECTIONS[][3] = { " +
                ", ".join("{ " + ", ".join(_c_float(x) for x in vertex) + " }"
                          for vertex in geosphere_directions) + " };",
                f"#define HCU_WIND_LOCAL_SEED 0x{LOCAL_SEED:08X}UL",
                "static const float hcu_wind_expected_normal[3] = { " +
                ", ".join(_c_float(value) for value in
                          expected[raw["weather_index"], "normal"]) + " };",
                "static const float hcu_wind_expected_simple[3] = { " +
                ", ".join(_c_float(value) for value in
                          expected[raw["weather_index"], "simple"]) + " };",
                "static const float hcu_wind_expected_damped[3] = { " +
                ", ".join(_c_float(value) for value in
                          expected[raw["weather_index"], "damped"]) + " };",
                "static const uint32_t HCU_WIND_DATUMS[] = { " +
                ", ".join(f"0x{row['datum']:08X}u" for row in rows) + " };",
                "static const float HCU_WIND_MAGNITUDES[] = { " +
                ", ".join(_c_float(row["magnitude"]) for row in rows) + " };",
                "static const float HCU_WIND_DIRECTIONS[][3] = { " +
                ", ".join("{ " + ", ".join(_c_float(x) for x in row["direction"]) + " }"
                          for row in rows) + " };",
                "static const float HCU_WIND_DEFINITIONS[][7] = { " +
                ", ".join("{ " + ", ".join(_c_float(x) for x in row["definition"]) + " }"
                          for row in rows) + " };",
            ]
            header.write_text("\n".join(lines) + "\n")

            semantics = temp / "halo_ps2_msvc_semantics.h"
            link_map = temp / "hcu-wind.map"
            executable = temp / "hcu-wind"
            subprocess.run([
                sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"),
                "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)
            includes = [
                temp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                HCU / "port/ps2/include", HCU / "port/include",
                HCU / "port/include/xdk", HCU / "port/linux/game",
                HCU / "source", HCU / "source/cseries", HCU / "source/scenario",
                HCU / "source/structures", HCU / "source/tag_files",
                HCU / "source/math", HCU / "source/memory", HCU / "source/game",
                HCU / "source/objects", HCU / "source/physics",
                Path("/usr/include"), Path("/usr/include/x86_64-linux-gnu"),
            ]
            command = [
                os.environ.get("CC", "cc"), *host_abi32_flags(),
                "-fshort-wchar", "-std=gnu99", "-fms-extensions", "-fcommon",
                "-fwrapv", "-fgnu89-inline", "-ffunction-sections", "-fdata-sections",
                "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
                "-DHALO_RELEASE=1", "-include",
                str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                "-include", str(semantics), "-w",
                *["-I" + str(path) for path in includes],
                "-Wl,--gc-sections", "-Wl,-Map=" + str(link_map),
                str(ROOT / "tests/hcu_wind_consumer_host32.c"),
                str(ROOT / "tests/hcu_real_math_host32.c"),
                str(HCU / "source/scenario/wind.c"),
                str(HCU / "source/scenario/scenario.c"),
                str(HCU / "source/math/random_math.c"),
                str(ROOT / "tests/hcu_geometry_source_host32.c"),
                str(ROOT / "tests/hcu_real_math_source_host32.c"),
                "-lm", "-o", str(executable),
            ]
            compiled = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0,
                             compiled.stdout + compiled.stderr)
            map_text = link_map.read_text()
            for symbol in ("wind_initialize_for_new_map", "wind_update",
                           "scenario_get_wind", "scenario_get_fog_region_index",
                           "seed_random_range", "seed_random_direction3d",
                           "geosphere_new", "geosphere_dispose",
                           "euler_angles2d_from_vector3d",
                           "vector3d_from_euler_angles2d"):
                self.assertIn(symbol, map_text,
                              f"wind integration closure omitted {symbol}")
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ce-wind map=a30 bsp=0 cluster=33 palette=0", run.stdout)
            self.assertIn("missing=zero repeat=stable status=passed", run.stdout)
            repeat = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 0, repeat.stdout + repeat.stderr)
            self.assertEqual(repeat.stdout, run.stdout)


if __name__ == "__main__":
    unittest.main()
