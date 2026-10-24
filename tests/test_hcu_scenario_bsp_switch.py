"""Execute the real CE BSP-switch body in a bounded host ILP32 fixture."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import hashlib
import json
import math
import os
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
STRUCTURE_BSP_SIZE = 648
STRUCTURE_BSP_CLUSTERS_OFFSET = 308
STRUCTURE_BSP_CLUSTER_DATA_OFFSET = 320
STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET = 532
STRUCTURE_BSP_WEATHER_PALETTE_OFFSET = 436
TAG_DATA_ADDRESS_OFFSET = 12
STRUCTURE_BSP_FOG_PLANES_OFFSET = 376
STRUCTURE_BSP_FOG_REGIONS_OFFSET = 388
STRUCTURE_BSP_FOG_PALETTE_OFFSET = 400
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402


def retail_source_pvs_pair_oracle(map_path, expected_bsp_count):
    """Derive first visible/hidden non-self PVS pairs from raw retail BSP bytes.

    This intentionally reads the original Xbox map extent, not CE's relocated
    global BSP or the HCU materializer's output. Layout offsets are pinned by
    the compiler-generated structure_bsp schema used by the package audit.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    result = []
    with Path(map_path).open("rb") as stream:
        for location in locations:
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")
            cluster_count = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_CLUSTERS_OFFSET)[0]
            pvs_bytes = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_CLUSTER_DATA_OFFSET)[0]
            pvs_address = struct.unpack_from(
                "<I", image,
                root + STRUCTURE_BSP_CLUSTER_DATA_OFFSET + TAG_DATA_ADDRESS_OFFSET)[0]
            pvs_offset = pvs_address - location.address
            sound_size = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET)[0]
            sound_address = struct.unpack_from(
                "<I", image, root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET +
                TAG_DATA_ADDRESS_OFFSET)[0]
            sound_offset = sound_address - location.address
            row_stride = ((cluster_count + 31) // 32) * 4
            required_bytes = row_stride * cluster_count
            required_sound_bytes = cluster_count * (cluster_count - 1) // 2
            if (cluster_count <= 1 or pvs_bytes < required_bytes or
                    pvs_offset < 0 or pvs_offset + required_bytes > len(image)):
                raise AssertionError(f"invalid source PVS extent for {location.path}")
            if (sound_size < required_sound_bytes or sound_offset < 0 or
                    sound_offset + required_sound_bytes > len(image)):
                raise AssertionError(f"invalid source sound extent for {location.path}")

            visible = None
            hidden = None
            for source_cluster in range(cluster_count):
                for target_cluster in range(cluster_count):
                    if source_cluster == target_cluster:
                        continue
                    word_offset = (pvs_offset + source_cluster * row_stride +
                                   (target_cluster // 32) * 4)
                    word = struct.unpack_from("<I", image, word_offset)[0]
                    pair = (source_cluster, target_cluster)
                    if word & (1 << (target_cluster & 31)):
                        if visible is None:
                            visible = pair
                    elif hidden is None:
                        hidden = pair
                    if visible is not None and hidden is not None:
                        break
                if visible is not None and hidden is not None:
                    break
            if visible is None or hidden is None:
                raise AssertionError(f"source PVS lacks visible/hidden pairs: {location.path}")
            hidden_reachable = None
            unreachable = None
            for from_cluster in range(cluster_count):
                for to_cluster in range(from_cluster + 1, cluster_count):
                    pvs_word = struct.unpack_from(
                        "<I", image,
                        pvs_offset + from_cluster * row_stride +
                        (to_cluster // 32) * 4)[0]
                    pvs_visible = bool(pvs_word & (1 << (to_cluster & 31)))
                    pair_index = (from_cluster * (cluster_count - 1) -
                                  from_cluster * (from_cluster + 1) // 2 +
                                  to_cluster - 1)
                    encoded_sound = image[sound_offset + pair_index]
                    if encoded_sound == 0xFF:
                        if unreachable is None:
                            unreachable = (from_cluster, to_cluster, encoded_sound,
                                          int(pvs_visible))
                    elif not pvs_visible and (encoded_sound & 0x7F) < 127:
                        if hidden_reachable is None:
                            hidden_reachable = (from_cluster, to_cluster, encoded_sound)
                    if hidden_reachable is not None and unreachable is not None:
                        break
                if hidden_reachable is not None and unreachable is not None:
                    break
            def read_block(block_offset, stride, label):
                count, address = struct.unpack_from("<iI", image, root + block_offset)
                if count < 0:
                    raise AssertionError(f"negative {label} block count for {location.path}")
                block_offset_in_image = address - location.address
                block_bytes = count * stride
                if count and (block_offset_in_image < 0 or
                              block_offset_in_image + block_bytes > len(image)):
                    raise AssertionError(f"{label} block leaves source BSP {location.path}")
                return count, block_offset_in_image

            clusters_size, clusters_offset = read_block(
                STRUCTURE_BSP_CLUSTERS_OFFSET, 0x68, "cluster")
            weather_palette_count, _weather_palette_offset = read_block(
                STRUCTURE_BSP_WEATHER_PALETTE_OFFSET, 0x74, "weather-palette")
            if clusters_size != cluster_count:
                raise AssertionError(f"cluster block count mismatch for {location.path}")
            underwater_weather = None
            for cluster_index in range(cluster_count):
                cluster_offset = clusters_offset + cluster_index * 0x68
                fog_reference = struct.unpack_from("<h", image, cluster_offset + 2)[0]
                if fog_reference == -1:
                    weather_index = struct.unpack_from(
                        "<h", image, cluster_offset + 8)[0]
                    expected_weather = (weather_index if
                        0 <= weather_index < weather_palette_count else -1)
                    underwater_weather = (cluster_index, weather_index,
                                          expected_weather)
                    break
            result.append({"clusters": cluster_count, "visible": visible,
                           "hidden": hidden, "hidden_reachable": hidden_reachable,
                           "unreachable": unreachable,
                           "underwater_weather": underwater_weather,
                           "path": location.path})
    return result


def retail_source_sound_environment_oracle(map_path, expected_bsp_count):
    """Derive one fog-free CE sound-palette result per raw retail BSP.

    The oracle reads the source Xbox BSP, not the converted package or the CE
    fixture's relocated pointers. Root and block offsets are pinned by the
    compiled CE schema; palette strides and tag-reference offsets are pinned
    by structure_bsp_definitions.h and tag_groups.h.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    structure_bsp_background_palette_offset = 508
    structure_bsp_sound_environment_palette_offset = 520
    structure_cluster_stride = 0x68
    sound_environment_palette_stride = 0x50
    background_sound_palette_stride = 0x74
    tag_reference_index_offset = 0x2C

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    results = {}
    with Path(map_path).open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")

            def read_block(offset, stride, label):
                count, address = struct.unpack_from("<iI", image, root + offset)
                if count < 0:
                    raise AssertionError(f"negative {label} block count in {location.path}")
                target = address - location.address
                extent = count * stride
                if count and (target < 0 or target + extent > len(image)):
                    raise AssertionError(f"{label} palette/cluster extent leaves {location.path}")
                return count, target

            cluster_count, cluster_offset = read_block(
                STRUCTURE_BSP_CLUSTERS_OFFSET, structure_cluster_stride, "cluster")
            background_count, background_offset = read_block(
                structure_bsp_background_palette_offset,
                background_sound_palette_stride, "background-sound")
            environment_count, environment_offset = read_block(
                structure_bsp_sound_environment_palette_offset,
                sound_environment_palette_stride, "sound-environment")
            for cluster_index in range(cluster_count):
                offset = cluster_offset + cluster_index * structure_cluster_stride
                fog_reference, background_index, environment_index = struct.unpack_from(
                    "<hhh", image, offset + 2)
                if (fog_reference != -1 or environment_index < 0 or
                        environment_index >= environment_count):
                    continue
                environment_tag = struct.unpack_from(
                    "<i", image, environment_offset +
                    environment_index * sound_environment_palette_stride +
                    tag_reference_index_offset)[0]
                if environment_tag == -1:
                    continue
                background_tag = -1
                if 0 <= background_index < background_count:
                    background_tag = struct.unpack_from(
                        "<i", image, background_offset +
                        background_index * background_sound_palette_stride +
                        tag_reference_index_offset)[0]
                results[bsp_index] = {
                    "bsp_index": bsp_index,
                    "cluster_index": cluster_index,
                    "palette_index": environment_index,
                    "environment_tag": environment_tag,
                    "background_tag": background_tag,
                    "path": location.path,
                }
                break
    return results


def retail_source_fog_plane_oracle(map_path, expected_bsp_count):
    """Select and decode valid retail fog-plane/region chains from Xbox BSPs."""
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    rows = []
    with Path(map_path).open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")

            def read_block(block_offset, stride, label):
                count, address = struct.unpack_from("<iI", image, root + block_offset)
                if count < 0:
                    raise AssertionError(f"negative {label} count in {location.path}")
                offset = address - location.address
                extent = count * stride
                if count and (offset < 0 or offset + extent > len(image)):
                    raise AssertionError(f"{label} extent leaves {location.path}")
                return count, offset

            cluster_count, clusters = read_block(STRUCTURE_BSP_CLUSTERS_OFFSET,
                                                  0x68, "cluster")
            plane_count, planes = read_block(STRUCTURE_BSP_FOG_PLANES_OFFSET,
                                              0x20, "fog-plane")
            region_count, regions = read_block(STRUCTURE_BSP_FOG_REGIONS_OFFSET,
                                                0x28, "fog-region")
            palette_count, palette = read_block(STRUCTURE_BSP_FOG_PALETTE_OFFSET,
                                                 0x88, "fog-palette")
            weather_count, _weather = read_block(STRUCTURE_BSP_WEATHER_PALETTE_OFFSET,
                                                  0x74, "weather-palette")
            for cluster_index in range(cluster_count):
                cluster = clusters + cluster_index * 0x68
                reference = struct.unpack_from("<h", image, cluster + 2)[0]
                if reference == -1 or not (reference & 0x8000):
                    continue
                plane_index = reference & 0x7FFF
                if plane_index >= plane_count:
                    continue
                plane = planes + plane_index * 0x20
                region_index = struct.unpack_from("<h", image, plane)[0]
                if not 0 <= region_index < region_count:
                    continue
                region = regions + region_index * 0x28
                fog_palette_index, region_weather = struct.unpack_from(
                    "<hh", image, region + 0x24)
                if not 0 <= fog_palette_index < palette_count:
                    continue
                fog_datum = struct.unpack_from(
                    "<i", image, palette + fog_palette_index * 0x88 + 0x2C)[0]
                if fog_datum == -1:
                    continue
                cluster_weather = struct.unpack_from("<h", image, cluster + 8)[0]
                weather = region_weather if region_weather != -1 else cluster_weather
                if not 0 <= weather < weather_count:
                    weather = -1
                normal = struct.unpack_from("<4f", image, plane + 4)
                if not any(normal[:3]):
                    raise AssertionError(f"zero fog-plane normal in {location.path}")
                rows.append({
                    "bsp_index": bsp_index, "cluster_index": cluster_index,
                    "reference": reference, "plane_index": plane_index,
                    "region_index": region_index,
                    "fog_palette_index": fog_palette_index,
                    "fog_datum": fog_datum,
                    "region_weather": region_weather,
                    "cluster_weather": cluster_weather,
                    "weather": weather, "plane": normal,
                    "path": location.path,
                })
                break
    return rows


def retail_source_fog_none_oracle(map_path, expected_bsp_count):
    """Derive one raw cluster NONE-fog reference per BSP, if present."""
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    result = []
    with Path(map_path).open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")
            cluster_count, cluster_address = struct.unpack_from(
                "<iI", image, root + STRUCTURE_BSP_CLUSTERS_OFFSET)
            cluster_offset = cluster_address - location.address
            if (cluster_count < 0 or cluster_offset < 0 or
                    cluster_offset + cluster_count * 0x68 > len(image)):
                raise AssertionError(f"cluster extent leaves {location.path}")
            for cluster_index in range(cluster_count):
                reference = struct.unpack_from(
                    "<h", image, cluster_offset + cluster_index * 0x68 + 2)[0]
                if reference == -1:
                    result.append({"bsp_index": bsp_index,
                                   "cluster_index": cluster_index,
                                   "reference": reference,
                                   "path": location.path})
                    break
    return result


def retail_source_sound_pas_oracle(map_path, expected_bsp_count):
    """Derive CE's combined audible-cluster set from raw Xbox BSP bytes.

    CE stores one byte for each unordered cluster pair. The high bit means
    unreachable; the low seven bits encode distance, with 127 mapping to the
    exclusive 256-unit cutoff. Listener clusters are selected from the raw
    matrix so two active players have observably distinct PAS rows.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    result = []
    with Path(map_path).open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")
            cluster_count = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_CLUSTERS_OFFSET)[0]
            size = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET)[0]
            address = struct.unpack_from(
                "<I", image,
                root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET +
                TAG_DATA_ADDRESS_OFFSET)[0]
            data_offset = address - location.address
            required = cluster_count * (cluster_count - 1) // 2
            if (cluster_count < 2 or size < required or data_offset < 0 or
                    data_offset + required > len(image)):
                raise AssertionError(f"invalid source sound-pair extent for {location.path}")

            def encoded_distance(left, right):
                if left == right:
                    return 0
                if left > right:
                    left, right = right, left
                offset = (left * (cluster_count - 1) -
                          left * (left + 1) // 2 + right - 1)
                if not 0 <= offset < size:
                    raise AssertionError(f"sound pair leaves extent in {location.path}")
                return image[data_offset + offset]

            encoded_values = image[data_offset:data_offset + required]
            noncanonical_high_bit_values = sorted({
                value for value in encoded_values
                if value & 0x80 and value != 0xFF
            })

            def audible_from(listener, cluster):
                encoded = encoded_distance(listener, cluster)
                # Match CE literally: bit 7 is masked off before the strict
                # distance comparison, despite its historical "unreachable"
                # enum name. 0x7f and 0xff both map to the exclusive cutoff.
                return (encoded & 0x7F) < 127

            selected = None
            rows = []
            for listener in range(cluster_count):
                rows.append([audible_from(listener, target)
                             for target in range(cluster_count)])
            for first in range(cluster_count):
                for second in range(first + 1, cluster_count):
                    if (any(a and not b for a, b in zip(rows[first], rows[second]))
                            and any(b and not a
                                    for a, b in zip(rows[first], rows[second]))):
                        selected = (first, second)
                        break
                if selected:
                    break
            if selected is None:
                # This BSP has no pair whose PAS rows contribute exclusive
                # audible clusters in both directions. Still exercise CE on
                # that BSP with one real listener; other BSPs must prove the
                # two-listener union explicitly.
                selected = (0, 0)
            first, second = selected
            expected = [int(rows[first][cluster] or rows[second][cluster])
                        for cluster in range(cluster_count)]
            words = [0] * 16
            for cluster, is_audible in enumerate(expected):
                if is_audible:
                    words[cluster // 32] |= 1 << (cluster % 32)
            result.append({
                "bsp_index": bsp_index,
                "clusters": cluster_count,
                "listener_clusters": [first, second, -1],
                "union_proved": int(first != second),
                "first_listener": [int(value) for value in rows[first]],
                "second_listener": [int(value) for value in rows[second]],
                "expected": expected,
                "words": words,
                "noncanonical_high_bit_values": noncanonical_high_bit_values,
                "path": location.path,
            })
    return result


def retail_source_player_pvs_oracle(map_path, expected_bsp_count):
    """Build raw-source CE-player PVS aggregation vectors for every BSP.

    The player cluster choices are selected solely from the raw Xbox PVS
    matrix.  Two players are local and one is non-local; the chosen non-local
    row must contribute at least one bit not present in the local union, so
    the local-player filter has an observable result.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source map BSP count differs from package catalog")

    result = []
    with Path(map_path).open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated source BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"source BSP root leaves {location.path}")
            cluster_count = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_CLUSTERS_OFFSET)[0]
            pvs_size = struct.unpack_from(
                "<i", image, root + STRUCTURE_BSP_CLUSTER_DATA_OFFSET)[0]
            pvs_address = struct.unpack_from(
                "<I", image, root + STRUCTURE_BSP_CLUSTER_DATA_OFFSET +
                TAG_DATA_ADDRESS_OFFSET)[0]
            pvs_offset = pvs_address - location.address
            words_per_row = (cluster_count + 31) // 32
            row_stride = words_per_row * 4
            required = cluster_count * row_stride
            if (cluster_count < 3 or pvs_size < required or pvs_offset < 0 or
                    pvs_offset + required > len(image)):
                raise AssertionError(f"invalid source PVS extent for {location.path}")
            rows = [list(struct.unpack_from(
                "<" + "I" * words_per_row,
                image, pvs_offset + cluster * row_stride))
                for cluster in range(cluster_count)]

            selected = None
            for local_a in range(cluster_count):
                for local_c in range(local_a + 1, cluster_count):
                    local_words = [0] * 16
                    for row_index in (local_a, local_c):
                        for word_index, word in enumerate(rows[row_index]):
                            local_words[word_index] |= word
                    for nonlocal_cluster in range(cluster_count):
                        if nonlocal_cluster in (local_a, local_c):
                            continue
                        all_words = local_words.copy()
                        for word_index, word in enumerate(rows[nonlocal_cluster]):
                            all_words[word_index] |= word
                        if all_words != local_words:
                            selected = (local_a, nonlocal_cluster, local_c,
                                        local_words, all_words)
                            break
                    if selected:
                        break
                if selected:
                    break
            if selected is None:
                raise AssertionError(
                    f"PVS rows do not expose local-player filtering in {location.path}")
            local_a, nonlocal_cluster, local_c, local_words, all_words = selected
            root_choice = None
            for root_cluster in range(cluster_count):
                if root_cluster == local_a:
                    continue
                root_local = [0] * 16
                root_all = [0] * 16
                for row_index in (root_cluster, local_c):
                    for word_index, word in enumerate(rows[row_index]):
                        root_local[word_index] |= word
                root_all = root_local.copy()
                for word_index, word in enumerate(rows[nonlocal_cluster]):
                    root_all[word_index] |= word
                if root_local != local_words:
                    root_choice = (root_cluster, root_local, root_all)
                    break
            if root_choice is None:
                raise AssertionError(
                    f"PVS rows do not expose object-root cluster refresh in {location.path}")
            root_cluster, root_local_words, root_all_words = root_choice
            result.append({
                "bsp_index": bsp_index,
                "clusters": cluster_count,
                "player_clusters": [local_a, nonlocal_cluster, local_c, -1],
                "root_cluster": root_cluster,
                "expected_local": local_words,
                "expected_all": all_words,
                "expected_root_local": root_local_words,
                "expected_root_all": root_all_words,
                "path": location.path,
            })
    return result


def retail_source_collision_goldens(map_path, expected_bsp_count,
                                    include_prisoner_directional=False,
                                    include_prisoner_breakable=False):
    """Derive isolated structure-hit queries from raw Xbox collision records.

    This is intentionally independent of CE's collision polygon and traversal
    routines. It reads the original collision surface/edge/vertex/plane arrays,
    analytically checks every polygon intersected by a candidate segment, and
    uses the serialized BSP3D tree to derive the start leaf, the last empty
    leaf immediately before surface contact, and their structure clusters.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, tag_region, header.decompressed_size)
    if len(locations) != expected_bsp_count:
        raise AssertionError("source collision BSP count differs from package catalog")

    def point_inside_convex_polygon(polygon, point, normal):
        drop = max(range(3), key=lambda axis: abs(normal[axis]))
        axes = [axis for axis in range(3) if axis != drop]
        sign = 0
        for first, second in zip(polygon, polygon[1:] + polygon[:1]):
            cross = ((second[axes[0]] - first[axes[0]]) *
                     (point[axes[1]] - first[axes[1]]) -
                     (second[axes[1]] - first[axes[1]]) *
                     (point[axes[0]] - first[axes[0]]))
            if abs(cross) < 1e-5:
                return False
            current = 1 if cross > 0.0 else -1
            if sign and current != sign:
                return False
            sign = current
        return True

    def coplanar_segment_overlaps_polygon(polygon, start, end, normal):
        """Inclusive 2-D overlap check after dropping the dominant normal axis."""
        drop = max(range(3), key=lambda axis: abs(normal[axis]))
        axes = [axis for axis in range(3) if axis != drop]
        poly = [(vertex[axes[0]], vertex[axes[1]]) for vertex in polygon]
        a = (start[axes[0]], start[axes[1]])
        b = (end[axes[0]], end[axes[1]])
        scale = max(1.0, *(abs(value) for pair in poly + [a, b] for value in pair))
        epsilon = 1.0e-8 * scale * scale

        def cross(u, v, w):
            return ((v[0] - u[0]) * (w[1] - u[1]) -
                    (v[1] - u[1]) * (w[0] - u[0]))

        def within(value, left, right):
            return min(left, right) - 1.0e-7 * scale <= value <= max(left, right) + 1.0e-7 * scale

        def point_on_segment(point, first, second):
            return (abs(cross(first, second, point)) <= epsilon and
                    within(point[0], first[0], second[0]) and
                    within(point[1], first[1], second[1]))

        def point_in_polygon(point):
            signs = []
            for first, second in zip(poly, poly[1:] + poly[:1]):
                value = cross(first, second, point)
                if abs(value) <= epsilon:
                    if point_on_segment(point, first, second):
                        return True
                else:
                    signs.append(value > 0.0)
            return not signs or all(sign == signs[0] for sign in signs)

        if point_in_polygon(a) or point_in_polygon(b):
            return True
        for first, second in zip(poly, poly[1:] + poly[:1]):
            o1, o2 = cross(a, b, first), cross(a, b, second)
            o3, o4 = cross(first, second, a), cross(first, second, b)
            if (((o1 > epsilon and o2 < -epsilon) or
                 (o1 < -epsilon and o2 > epsilon)) and
                ((o3 > epsilon and o4 < -epsilon) or
                 (o3 < -epsilon and o4 > epsilon))):
                return True
            if (abs(o1) <= epsilon and point_on_segment(first, a, b)) or \
                    (abs(o2) <= epsilon and point_on_segment(second, a, b)) or \
                    (abs(o3) <= epsilon and point_on_segment(a, first, second)) or \
                    (abs(o4) <= epsilon and point_on_segment(b, first, second)):
                return True
        return False

    result = []
    with Path(map_path).open("rb") as stream:
        for location_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise AssertionError(f"truncated raw collision BSP {location.path}")
            root_address = struct.unpack_from("<I", image, 0)[0]
            root = root_address - location.address
            if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
                raise AssertionError(f"raw structure BSP root leaves {location.path}")

            def read_block(base, offset, stride, label):
                count, address = struct.unpack_from("<II", image, base + offset)
                if count < 0:
                    raise AssertionError(f"negative {label} count for {location.path}")
                data_offset = address - location.address
                if count and (data_offset < 0 or
                              data_offset + count * stride > len(image)):
                    raise AssertionError(f"raw {label} block leaves {location.path}")
                return count, data_offset, stride

            material_count, materials_offset, material_stride = read_block(
                root, 0x0A4, 20, "collision-material")
            collision_count, collision_offset, _ = read_block(
                root, 0x0B0, 96, "collision-bsp")
            if collision_count != 1:
                raise AssertionError(f"expected one collision BSP in {location.path}")
            nodes = read_block(collision_offset, 0x00, 12, "BSP3D-node")
            planes = read_block(collision_offset, 0x0C, 16, "collision-plane")
            collision_leaves = read_block(collision_offset, 0x18, 8,
                                          "collision-leaf")
            bsp2d_references = read_block(collision_offset, 0x24, 8,
                                          "BSP2D-reference")
            bsp2d_nodes = read_block(collision_offset, 0x30, 20,
                                     "BSP2D-node")
            surfaces = read_block(collision_offset, 0x3C, 12,
                                  "collision-surface")
            edges = read_block(collision_offset, 0x48, 24, "collision-edge")
            vertices = read_block(collision_offset, 0x54, 16,
                                  "collision-vertex")
            structure_leaves = read_block(root, 0x0E0, 16, "structure-leaf")
            if structure_leaves[0] != collision_leaves[0]:
                raise AssertionError(f"collision/structure leaf counts differ in {location.path}")

            decoded_polygons = []
            for surface_index in range(surfaces[0]):
                surface_offset = surfaces[1] + surface_index * surfaces[2]
                plane_designator, first_edge, flags, breakable_index, material_index = (
                    struct.unpack_from("<iiBBh", image, surface_offset))
                edge_index = first_edge
                seen_edges = set()
                polygon = []
                for _ in range(9):
                    if edge_index in seen_edges or not 0 <= edge_index < edges[0]:
                        polygon = []
                        break
                    seen_edges.add(edge_index)
                    edge_offset = edges[1] + edge_index * edges[2]
                    (vertex0, vertex1, edge0, edge1,
                     surface0, surface1) = struct.unpack_from("<6i", image, edge_offset)
                    reverse = int(surface1 == surface_index)
                    if (surface0, surface1)[reverse] != surface_index:
                        polygon = []
                        break
                    vertex_index = (vertex0, vertex1)[reverse]
                    if not 0 <= vertex_index < vertices[0]:
                        polygon = []
                        break
                    polygon.append(struct.unpack_from("<3f", image,
                        vertices[1] + vertex_index * vertices[2]))
                    edge_index = (edge0, edge1)[reverse]
                    if edge_index == first_edge:
                        break
                if len(polygon) < 3 or len(polygon) > 8 or edge_index != first_edge:
                    decoded_polygons.append(None)
                    continue
                plane_index = plane_designator & 0x7FFFFFFF
                if not 0 <= plane_index < planes[0]:
                    decoded_polygons.append(None)
                    continue
                plane = struct.unpack_from("<4f", image,
                    planes[1] + plane_index * planes[2])
                decoded_polygons.append({
                    "index": surface_index, "plane_designator": plane_designator,
                    "plane_index": plane_index, "plane": plane,
                    "flags": flags, "breakable_index": breakable_index,
                    "material_index": material_index, "polygon": polygon,
                })

            def tree_leaf(point):
                node_index = 0
                visited = set()
                for _ in range(nodes[0] + 1):
                    if node_index & 0x80000000:
                        leaf_index = node_index & 0x7FFFFFFF
                        if leaf_index >= collision_leaves[0]:
                            raise AssertionError(
                                f"BSP3D child leaf {leaf_index} leaves the "
                                f"collision leaf block in {location.path}")
                        return leaf_index, visited
                    if node_index in visited or not 0 <= node_index < nodes[0]:
                        raise AssertionError(f"invalid BSP3D traversal in {location.path}")
                    visited.add(node_index)
                    node_offset = nodes[1] + node_index * nodes[2]
                    plane_index, back_child, front_child = struct.unpack_from(
                        "<3I", image, node_offset)
                    if plane_index >= planes[0]:
                        raise AssertionError(f"BSP3D node plane out of range in {location.path}")
                    plane = struct.unpack_from("<4f", image,
                        planes[1] + plane_index * planes[2])
                    distance = sum(plane[axis] * point[axis] for axis in range(3)) - plane[3]
                    node_index = front_child if distance >= 0.0 else back_child
                    if node_index == 0xFFFFFFFF:
                        return -1, visited
                raise AssertionError(f"BSP3D traversal exceeds node count in {location.path}")

            def ce_leaf_surface(leaf_index, plane_designator, hit_point):
                """Mirror CE's leaf reference/BSP2D selection from serialized data."""
                plane_index = plane_designator & 0x7FFFFFFF
                plane = struct.unpack_from("<4f", image,
                    planes[1] + plane_index * planes[2])
                normal = plane[:3]
                drop = max(range(3), key=lambda axis: abs(normal[axis]))
                if drop == 2:
                    projection = 2
                    sign = normal[2] > 0.0
                elif drop == 1:
                    projection = 1
                    sign = normal[1] > 0.0
                else:
                    projection = 0
                    sign = normal[0] > 0.0
                sign = sign != bool(plane_designator & 0x80000000)
                leaf_offset = collision_leaves[1] + leaf_index * collision_leaves[2]
                _flags, reference_count, first_reference = struct.unpack_from(
                    "<HhI", image, leaf_offset)
                if first_reference + reference_count > bsp2d_references[0]:
                    raise AssertionError("raw leaf BSP2D references leave their block")
                for reference_index in range(first_reference,
                                             first_reference + reference_count):
                    ref_offset = bsp2d_references[1] + reference_index * bsp2d_references[2]
                    designator, node_index = struct.unpack_from("<II", image, ref_offset)
                    if (designator & 0x7FFFFFFF) != plane_index:
                        continue
                    ref_sign = (normal[projection] > 0.0) != bool(
                        designator & 0x80000000)
                    mappings = (((2, 1), (1, 2)),
                                ((0, 2), (2, 0)),
                                ((1, 0), (0, 1)))
                    x_axis, y_axis = mappings[projection][int(ref_sign)]
                    p2 = (hit_point[x_axis], hit_point[y_axis])
                    for _ in range(bsp2d_nodes[0] + 1):
                        if node_index & 0x80000000:
                            surface_index = node_index & 0x7FFFFFFF
                            return surface_index if surface_index < surfaces[0] else None
                        if node_index >= bsp2d_nodes[0]:
                            raise AssertionError("raw BSP2D node leaves block")
                        node_offset = bsp2d_nodes[1] + node_index * bsp2d_nodes[2]
                        ni, nj, distance, child0, child1 = struct.unpack_from(
                            "<3fII", image, node_offset)
                        node_index = (child1 if ni * p2[0] + nj * p2[1] - distance >= 0.0
                                      else child0)
                    raise AssertionError("raw BSP2D traversal exceeds node count")
                return None

            selected = None
            selected_candidate = None
            for candidate in decoded_polygons:
                if candidate is None or candidate["flags"] != 0:
                    continue
                material_index = candidate["material_index"]
                if not 0 <= material_index < material_count:
                    continue
                material_type = struct.unpack_from("<h", image,
                    materials_offset + material_index * material_stride + 18)[0]
                if not 0 <= material_type < 32:
                    continue
                raw_plane = candidate["plane"]
                oriented_plane = (tuple(-value for value in raw_plane)
                    if candidate["plane_designator"] & 0x80000000 else raw_plane)
                normal = oriented_plane[:3]
                magnitude = math.sqrt(sum(value * value for value in normal))
                if not 0.9 < magnitude < 1.1:
                    continue
                unit_normal = tuple(value / magnitude for value in normal)
                polygon = candidate["polygon"]
                center = tuple(sum(vertex[axis] for vertex in polygon) / len(polygon)
                               for axis in range(3))
                plane_error = abs(sum(oriented_plane[axis] * center[axis]
                                      for axis in range(3)) - oriented_plane[3])
                if (plane_error > 0.002 or
                        not point_inside_convex_polygon(polygon, center, unit_normal)):
                    continue

                for direction in (1.0, -1.0):
                    start = tuple(center[axis] + direction * unit_normal[axis] * 0.5
                                  for axis in range(3))
                    vector = tuple(-direction * unit_normal[axis] for axis in range(3))
                    start_leaf, start_path = tree_leaf(start)
                    outside_leaf, outside_path = tree_leaf(
                        tuple(start[axis] + vector[axis] for axis in range(3)))
                    if start_leaf < 0 or outside_leaf != -1:
                        continue

                    hits = []
                    for polygon_row in decoded_polygons:
                        if polygon_row is None:
                            continue
                        plane = polygon_row["plane"]
                        denominator = sum(plane[axis] * vector[axis]
                                          for axis in range(3))
                        if abs(denominator) < 1e-9:
                            continue
                        t = (plane[3] - sum(plane[axis] * start[axis]
                                            for axis in range(3))) / denominator
                        if not -1e-5 <= t <= 1.00001:
                            continue
                        point = tuple(start[axis] + t * vector[axis]
                                      for axis in range(3))
                        if point_inside_convex_polygon(
                                polygon_row["polygon"], point, plane[:3]):
                            hits.append((t, polygon_row["index"], point))
                    hits.sort(key=lambda item: item[0])
                    if (len(hits) != 1 or hits[0][1] != candidate["index"] or
                            not 0.1 < hits[0][0] < 0.9):
                        continue

                    # CE records the last leaf visited before the first solid
                    # collision. Derive that location independently from the
                    # raw BSP3D tree just before the analytically computed
                    # surface intersection.
                    hit_t = hits[0][0]
                    contact_point = tuple(
                        start[axis] + max(0.0, hit_t - 1.0e-4) * vector[axis]
                        for axis in range(3))
                    contact_leaf, _contact_path = tree_leaf(contact_point)
                    if start_leaf < 0 or contact_leaf < 0:
                        continue
                    # A raw polygon intersection is not sufficient: CE only
                    # tests surfaces reachable through this BSP3D leaf's
                    # serialized BSP2D reference set. Derive that selection
                    # independently and reject candidates CE cannot select.
                    selected_surface = ce_leaf_surface(
                        start_leaf, candidate["plane_designator"],
                        tuple(start[axis] + hit_t * vector[axis]
                              for axis in range(3)))
                    if selected_surface != candidate["index"]:
                        continue
                    leaf_offset = structure_leaves[1] + start_leaf * structure_leaves[2]
                    cluster_index = struct.unpack_from("<h", image, leaf_offset + 8)[0]
                    if cluster_index < 0:
                        continue
                    location_offset = (structure_leaves[1] +
                                       contact_leaf * structure_leaves[2])
                    location_cluster = struct.unpack_from(
                        "<h", image, location_offset + 8)[0]
                    if location_cluster < 0:
                        continue
                    expected_plane = oriented_plane
                    t = hits[0][0]
                    hit_point = hits[0][2]
                    selected = {
                        "bsp_index": location_index, "path": location.path,
                        "surface_index": candidate["index"],
                        "material_index": material_index,
                        "material_type": material_type,
                        "plane_designator": candidate["plane_designator"],
                        "plane": expected_plane, "start": start,
                        "vector": vector, "t": t, "point": hit_point,
                        "leaf_index": start_leaf, "cluster_index": cluster_index,
                        "location_leaf_index": contact_leaf,
                        "location_cluster_index": location_cluster,
                        "raw_start_leaf": start_leaf, "raw_end_leaf": outside_leaf,
                    }
                    selected_candidate = candidate
                    break
                if selected:
                    break

            if selected is None:
                raise AssertionError(f"no unique raw-geometry collision golden for {location.path}")
            if (location.path == "levels\\a50\\a50_muster" or
                    (include_prisoner_directional and
                     location.path == "levels\\test\\prisoner\\prisoner")):
                # Add a same-empty-leaf miss and the exact reverse of the
                # source-derived hit. This is deliberately limited to the
                # audited a50 muster BSP; the other map/BSP rows remain hit
                # goldens only. Refuse the miss oracle if any raw surface
                # record could not be decoded, so "no hit" is not inferred
                # from a partial polygon set. Prisoner opts into the same
                # independent directional proof for the multiplayer fixture.
                if any(candidate is None for candidate in decoded_polygons):
                    raise AssertionError(
                        f"cannot prove all raw polygons for miss case in {location.path}")

                def source_segment_hits(start_point, movement):
                    intersections = []
                    for polygon_row in decoded_polygons:
                        plane = polygon_row["plane"]
                        denominator = sum(plane[axis] * movement[axis]
                                          for axis in range(3))
                        if abs(denominator) < 1e-9:
                            start_distance = (sum(plane[axis] * start_point[axis]
                                                  for axis in range(3)) - plane[3])
                            end_point = tuple(start_point[axis] + movement[axis]
                                              for axis in range(3))
                            end_distance = (sum(plane[axis] * end_point[axis]
                                                for axis in range(3)) - plane[3])
                            normal_length = math.sqrt(sum(value * value
                                                          for value in plane[:3]))
                            coordinate_scale = max(1.0, *(abs(value) for value in
                                tuple(start_point) + tuple(end_point)))
                            plane_tolerance = 1.0e-6 * max(
                                1.0, abs(plane[3]), normal_length * coordinate_scale)
                            if (abs(start_distance) <= plane_tolerance and
                                    abs(end_distance) <= plane_tolerance and
                                    coplanar_segment_overlaps_polygon(
                                        polygon_row["polygon"], start_point,
                                        end_point, plane[:3])):
                                intersections.append((0.0, polygon_row["index"],
                                                      tuple(start_point)))
                            continue
                        t = (plane[3] - sum(plane[axis] * start_point[axis]
                                            for axis in range(3))) / denominator
                        if not -1e-5 <= t <= 1.00001:
                            continue
                        point = tuple(start_point[axis] + t * movement[axis]
                                      for axis in range(3))
                        if point_inside_convex_polygon(
                                polygon_row["polygon"], point,
                                polygon_row["plane"][:3]):
                            intersections.append((t, polygon_row["index"], point))
                    intersections.sort(key=lambda item: item[0])
                    return intersections

                miss_start = selected["start"]
                miss_vector = tuple(-component * 0.25
                                    for component in selected["vector"])
                miss_end = tuple(miss_start[axis] + miss_vector[axis]
                                 for axis in range(3))
                miss_start_leaf, _ = tree_leaf(miss_start)
                miss_end_leaf, _ = tree_leaf(miss_end)
                if (miss_start_leaf < 0 or miss_end_leaf != miss_start_leaf or
                        source_segment_hits(miss_start, miss_vector)):
                    raise AssertionError(
                        f"candidate short miss is not source-proven in {location.path}")
                miss_leaf_offset = (structure_leaves[1] +
                                    miss_start_leaf * structure_leaves[2])
                miss_cluster = struct.unpack_from(
                    "<h", image, miss_leaf_offset + 8)[0]
                if miss_cluster < 0:
                    raise AssertionError(
                        f"candidate miss leaf lacks a cluster in {location.path}")

                reverse_start = tuple(selected["start"][axis] +
                                      selected["vector"][axis]
                                      for axis in range(3))
                reverse_vector = tuple(-component for component in selected["vector"])
                reverse_hits = source_segment_hits(reverse_start, reverse_vector)
                reverse_end = tuple(reverse_start[axis] + reverse_vector[axis]
                                    for axis in range(3))
                reverse_start_leaf, _ = tree_leaf(reverse_start)
                reverse_end_leaf, _ = tree_leaf(reverse_end)
                if (len(reverse_hits) != 1 or
                        reverse_hits[0][1] != selected_candidate["index"] or
                        reverse_start_leaf != -1 or
                        reverse_end_leaf != selected["leaf_index"]):
                    raise AssertionError(
                        f"reverse collision case is not source-proven in {location.path}")
                selected["directional_cases"] = {
                    "miss": {
                        "start": miss_start, "vector": miss_vector,
                        "start_leaf": miss_start_leaf,
                        "end_leaf": miss_end_leaf,
                        "cluster": miss_cluster,
                    },
                    "reverse": {
                        "start": reverse_start, "vector": reverse_vector,
                        "t": reverse_hits[0][0], "point": reverse_hits[0][2],
                        "surface_index": reverse_hits[0][1],
                        "solid_leaf": reverse_start_leaf,
                        "empty_leaf": reverse_end_leaf,
                    },
                }
            if location.path == "levels\\a30\\a30_a":
                # Derive both rays from the raw shared edge of surfaces 27
                # and 94 rather than copying CE's collision output. The
                # +/-0.01 in-plane offsets make each contact uniquely inside
                # one polygon; an exact-edge midpoint is deliberately not a
                # pass/fail case because float/BSP2D tie rounding is separate.
                if any(candidate is None for candidate in decoded_polygons):
                    raise AssertionError("a30 edge oracle needs every raw surface decoded")
                first_surface = decoded_polygons[27]
                second_surface = decoded_polygons[94]
                shared = [point for point in first_surface["polygon"]
                          if point in second_surface["polygon"]]
                if (len(shared) != 2 or first_surface["flags"] != 0 or
                        second_surface["flags"] != 0 or
                        first_surface["material_index"] != 3 or
                        second_surface["material_index"] != 3):
                    raise AssertionError("a30 raw shared-edge source records changed")
                midpoint = tuple((shared[0][axis] + shared[1][axis]) * 0.5
                                 for axis in range(3))
                raw_plane = first_surface["plane"]
                norm_length = math.sqrt(sum(value * value for value in raw_plane[:3]))
                normal = tuple(value / norm_length for value in raw_plane[:3])
                first_center = tuple(sum(point[axis] for point in
                    first_surface["polygon"]) / len(first_surface["polygon"])
                    for axis in range(3))
                inward = tuple(first_center[axis] - midpoint[axis]
                               for axis in range(3))
                projection = sum(inward[axis] * normal[axis] for axis in range(3))
                inward = tuple(inward[axis] - projection * normal[axis]
                               for axis in range(3))
                inward_length = math.sqrt(sum(value * value for value in inward))
                inward = tuple(value / inward_length for value in inward)
                edge_cases = []
                for epsilon, expected_surface in ((0.01, 27), (-0.01, 94)):
                    contact = tuple(midpoint[axis] + epsilon * inward[axis]
                                    for axis in range(3))
                    start = tuple(contact[axis] + 0.5 * normal[axis]
                                  for axis in range(3))
                    vector = tuple(-value for value in normal)
                    intersections = []
                    for polygon_row in decoded_polygons:
                        plane = polygon_row["plane"]
                        denominator = sum(plane[axis] * vector[axis]
                                          for axis in range(3))
                        if abs(denominator) < 1e-9:
                            continue
                        t = (plane[3] - sum(plane[axis] * start[axis]
                                            for axis in range(3))) / denominator
                        if not 0.0 <= t <= 1.0:
                            continue
                        point = tuple(start[axis] + t * vector[axis]
                                      for axis in range(3))
                        if point_inside_convex_polygon(
                                polygon_row["polygon"], point, plane[:3]):
                            intersections.append((t, polygon_row["index"], point))
                    if (len(intersections) != 1 or
                            intersections[0][1] != expected_surface):
                        raise AssertionError(
                            f"raw shared-edge ray is not unique for surface {expected_surface}")
                    hit_t, _surface, point = intersections[0]
                    start_leaf, _ = tree_leaf(start)
                    end_point = tuple(start[axis] + vector[axis] for axis in range(3))
                    end_leaf, _ = tree_leaf(end_point)
                    precontact = tuple(start[axis] + max(0.0, hit_t - 1.0e-4) *
                                       vector[axis] for axis in range(3))
                    precontact_leaf, _ = tree_leaf(precontact)
                    expected_precontact_leaf = 10114 if expected_surface == 27 else 10113
                    if (start_leaf != 10114 or end_leaf != -1 or
                            precontact_leaf != expected_precontact_leaf):
                        raise AssertionError("a30 shared-edge BSP3D path changed")
                    polygon_row = decoded_polygons[expected_surface]
                    edge_cases.append({
                        "surface_index": expected_surface,
                        "material_index": 3,
                        "plane_designator": polygon_row["plane_designator"],
                        "flags": polygon_row["flags"],
                        "breakable_index": polygon_row["breakable_index"],
                        "start": start, "vector": vector, "t": hit_t,
                        "point": point, "start_leaf": start_leaf,
                        "precontact_leaf": precontact_leaf, "end_leaf": end_leaf,
                    })
                selected["shared_edge_cases"] = edge_cases
                flagged_cases = {}
                for case_name, flag_mask, require_not_mask in (
                        ("invisible", 1 << 1, 1 << 3),
                        ("breakable", 1 << 3, 0)):
                    for polygon_row in decoded_polygons:
                        if (not polygon_row["flags"] & flag_mask or
                                polygon_row["flags"] & require_not_mask):
                            continue
                        plane = polygon_row["plane"]
                        norm_length = math.sqrt(sum(value * value for value in plane[:3]))
                        if not 0.9 < norm_length < 1.1:
                            continue
                        normal = tuple(value / norm_length for value in plane[:3])
                        polygon = polygon_row["polygon"]
                        center = tuple(sum(vertex[axis] for vertex in polygon) /
                                       len(polygon) for axis in range(3))
                        for direction in (1.0, -1.0):
                            start = tuple(center[axis] + direction * normal[axis] * 0.5
                                          for axis in range(3))
                            vector = tuple(-direction * value for value in normal)
                            intersections = []
                            for candidate in decoded_polygons:
                                candidate_plane = candidate["plane"]
                                denominator = sum(candidate_plane[axis] * vector[axis]
                                                  for axis in range(3))
                                if abs(denominator) < 1e-9:
                                    continue
                                t = (candidate_plane[3] - sum(
                                    candidate_plane[axis] * start[axis]
                                    for axis in range(3))) / denominator
                                if not 0.0 <= t <= 1.0:
                                    continue
                                point = tuple(start[axis] + t * vector[axis]
                                              for axis in range(3))
                                if point_inside_convex_polygon(
                                        candidate["polygon"], point,
                                        candidate_plane[:3]):
                                    intersections.append((t, candidate["index"], point))
                            if not intersections:
                                continue
                            hit_t, _surface, point = min(intersections)
                            start_leaf, _ = tree_leaf(start)
                            if start_leaf < 0:
                                continue
                            selected_surface = ce_leaf_surface(
                                start_leaf, polygon_row["plane_designator"], point)
                            if selected_surface != polygon_row["index"]:
                                continue
                            end = tuple(start[axis] + vector[axis] for axis in range(3))
                            end_leaf, _ = tree_leaf(end)
                            precontact = tuple(start[axis] + max(0.0, hit_t - 1.0e-4) *
                                               vector[axis] for axis in range(3))
                            precontact_leaf, _ = tree_leaf(precontact)
                            if precontact_leaf < 0:
                                continue
                            if (case_name == "breakable" and
                                    polygon_row["breakable_index"] >= 256):
                                continue
                            flagged_cases[case_name] = {
                                "surface_index": polygon_row["index"],
                                "material_index": polygon_row["material_index"],
                                "plane_designator": polygon_row["plane_designator"],
                                "flags": polygon_row["flags"],
                                "breakable_index": polygon_row["breakable_index"],
                                "start": start, "vector": vector, "t": hit_t,
                                "point": point, "start_leaf": start_leaf,
                                "precontact_leaf": precontact_leaf,
                                "end_leaf": end_leaf,
                            }
                            break
                        if case_name in flagged_cases:
                            break
                if set(flagged_cases) != {"invisible", "breakable"}:
                    raise AssertionError(
                        f"a30 B000 lacks CE-selected flagged collision query candidates: "
                        f"{sorted(flagged_cases)}")
                selected["flagged_cases"] = flagged_cases
            elif (include_prisoner_breakable and
                  location.path == "levels\\test\\prisoner\\prisoner"):
                # Prisoner's breakable case is a multiplayer-only counterpart
                # to the historical a30 test. Require complete raw polygon
                # coverage, a unique segment/polygon contact, raw BSP3D
                # empty-to-solid traversal, and the serialized BSP2D result;
                # never derive the expected face from CE's returned hit.
                if any(candidate is None for candidate in decoded_polygons):
                    raise AssertionError(
                        "Prisoner breakable oracle requires every surface decoded")
                breakable_case = None
                for polygon_row in decoded_polygons:
                    if (not polygon_row["flags"] & (1 << 3) or
                            polygon_row["breakable_index"] >= 256):
                        continue
                    plane = polygon_row["plane"]
                    norm_length = math.sqrt(sum(value * value for value in plane[:3]))
                    if not 0.9 < norm_length < 1.1:
                        continue
                    normal = tuple(value / norm_length for value in plane[:3])
                    polygon = polygon_row["polygon"]
                    center = tuple(sum(vertex[axis] for vertex in polygon) /
                                   len(polygon) for axis in range(3))
                    if not point_inside_convex_polygon(polygon, center, normal):
                        continue
                    for direction in (1.0, -1.0):
                        start = tuple(center[axis] + direction * normal[axis] * 0.5
                                      for axis in range(3))
                        vector = tuple(-direction * value for value in normal)
                        start_leaf, _ = tree_leaf(start)
                        end = tuple(start[axis] + vector[axis] for axis in range(3))
                        end_leaf, _ = tree_leaf(end)
                        if start_leaf < 0 or end_leaf < 0:
                            continue
                        intersections = []
                        for candidate in decoded_polygons:
                            candidate_plane = candidate["plane"]
                            denominator = sum(candidate_plane[axis] * vector[axis]
                                              for axis in range(3))
                            if abs(denominator) < 1e-9:
                                continue
                            t = (candidate_plane[3] - sum(
                                candidate_plane[axis] * start[axis]
                                for axis in range(3))) / denominator
                            if not 0.0 <= t <= 1.0:
                                continue
                            point = tuple(start[axis] + t * vector[axis]
                                          for axis in range(3))
                            if point_inside_convex_polygon(
                                    candidate["polygon"], point,
                                    candidate_plane[:3]):
                                intersections.append((t, candidate["index"], point))
                        intersections.sort(key=lambda item: item[0])
                        if (len(intersections) < 2 or
                                not 0.1 < intersections[0][0] < 0.9):
                            continue
                        t, _surface, point = intersections[0]
                        group_rows = [decoded_polygons[surface_index]
                                      for _t, surface_index, _point in intersections]
                        same_coplanar_breakable_group = all(
                            row["flags"] & (1 << 3) and
                            row["breakable_index"] == polygon_row["breakable_index"] and
                            row["material_index"] == polygon_row["material_index"] and
                            abs(_t - t) <= 1.0e-6 and
                            max(abs(_point[axis] - point[axis]) for axis in range(3))
                                <= 1.0e-5 and
                            all(abs(abs(row["plane"][axis]) -
                                    abs(polygon_row["plane"][axis])) <= 1.0e-5
                                for axis in range(4))
                            for row, (_t, _surface_index, _point) in
                                zip(group_rows, intersections))
                        if not same_coplanar_breakable_group:
                            continue
                        precontact = tuple(start[axis] + max(0.0, t - 1.0e-4) *
                                           vector[axis] for axis in range(3))
                        precontact_leaf, _ = tree_leaf(precontact)
                        selected_surface = ce_leaf_surface(
                            start_leaf, polygon_row["plane_designator"], point)
                        group_indices = [row["index"] for row in group_rows]
                        if (precontact_leaf < 0 or
                                selected_surface not in group_indices):
                            continue
                        selected_row = decoded_polygons[selected_surface]
                        start_cluster = struct.unpack_from(
                            "<h", image, structure_leaves[1] +
                            start_leaf * structure_leaves[2] + 8)[0]
                        precontact_cluster = struct.unpack_from(
                            "<h", image, structure_leaves[1] +
                            precontact_leaf * structure_leaves[2] + 8)[0]
                        if start_cluster < 0 or precontact_cluster < 0:
                            continue
                        breakable_case = {
                            "surface_index": selected_surface,
                            "surface_group": sorted(group_indices),
                            "material_index": selected_row["material_index"],
                            "plane_designator": selected_row["plane_designator"],
                            "flags": selected_row["flags"],
                            "breakable_index": selected_row["breakable_index"],
                            "start": start, "vector": vector, "t": t,
                            "point": point, "start_leaf": start_leaf,
                            "start_cluster": start_cluster,
                            "precontact_leaf": precontact_leaf,
                            "precontact_cluster": precontact_cluster,
                            "end_leaf": end_leaf,
                        }
                        break
                    if breakable_case is not None:
                        break
                if breakable_case is None:
                    raise AssertionError(
                        "Prisoner has no uniquely source-proven CE-selected breakable ray")
                selected["flagged_cases"] = {"breakable": breakable_case}
            result.append(selected)
    return result


def write_collision_golden_header(path, rows):
    """Write raw-source collision expectations for the native CE fixture."""
    lines = [
        "typedef struct hcu_raw_collision_golden {",
        "    int map_id, bsp_index, surface_index, material_index, material_type;",
        "    int plane_designator, leaf_index, cluster_index;",
        "    int location_leaf_index, location_cluster_index;",
        "    float start[3], vector[3], plane[4], t, point[3];",
        "} hcu_raw_collision_golden;",
        "typedef struct hcu_raw_collision_directional_golden {",
        "    int map_id, bsp_index, miss_leaf, miss_cluster, reverse_surface;",
        "    float miss_start[3], miss_vector[3], miss_t;",
        "    float reverse_start[3], reverse_vector[3], reverse_t, reverse_point[3];",
        "} hcu_raw_collision_directional_golden;",
        "static const hcu_raw_collision_golden hcu_raw_collision_goldens[] = {",
    ]

    def f(value):
        literal = f"{float(value):.9g}"
        if "." not in literal and "e" not in literal.lower():
            literal += ".0"
        return literal + "f"

    directional_rows = []
    shared_edge_rows = []
    flagged_rows = []
    for map_id, goldens in rows:
        for row in goldens:
            fields = [map_id, row["bsp_index"], row["surface_index"],
                      row["material_index"], row["material_type"],
                      row["plane_designator"], row["leaf_index"],
                      row["cluster_index"], row["location_leaf_index"],
                      row["location_cluster_index"]]
            arrays = [row["start"], row["vector"], row["plane"],
                      (row["t"],), row["point"]]
            initializer = ", ".join(str(value) for value in fields)
            initializer += ", " + ", ".join(
                "{" + ", ".join(f(value) for value in values) + "}"
                for values in arrays)
            lines.append("    {" + initializer + "},")
            cases = row.get("directional_cases")
            if cases:
                miss = cases["miss"]
                reverse = cases["reverse"]
                directional_rows.append((
                    map_id, row["bsp_index"], miss["start_leaf"],
                    miss["cluster"], reverse["surface_index"],
                    miss["start"], miss["vector"],
                    reverse["start"], reverse["vector"],
                    reverse["t"], reverse["point"],
                ))
            if row.get("shared_edge_cases"):
                shared_edge_rows.append((map_id, row["bsp_index"],
                                         row["shared_edge_cases"]))
            for case_name, case in row.get("flagged_cases", {}).items():
                flagged_rows.append((map_id, row["bsp_index"],
                                     1 if case_name == "invisible" else 2, case))
    lines.extend([
        "};",
        "#define HCU_RAW_COLLISION_GOLDEN_COUNT "
        "(sizeof(hcu_raw_collision_goldens) / sizeof(hcu_raw_collision_goldens[0]))",
        "static const hcu_raw_collision_directional_golden "
        "hcu_raw_collision_directional_goldens[] = {",
    ])
    for (map_id, bsp_index, miss_leaf, miss_cluster, reverse_surface,
         miss_start, miss_vector, reverse_start, reverse_vector,
         reverse_t, reverse_point) in directional_rows:
        fields = [map_id, bsp_index, miss_leaf, miss_cluster, reverse_surface]
        arrays = [miss_start, miss_vector, (1.0,), reverse_start,
                  reverse_vector, (reverse_t,), reverse_point]
        initializer = ", ".join(str(value) for value in fields)
        initializer += ", " + ", ".join(
            "{" + ", ".join(f(value) for value in values) + "}"
            for values in arrays)
        lines.append("    {" + initializer + "},")
    lines.extend([
        "};",
        "#define HCU_RAW_COLLISION_DIRECTIONAL_GOLDEN_COUNT "
        "(sizeof(hcu_raw_collision_directional_goldens) / "
        "sizeof(hcu_raw_collision_directional_goldens[0]))",
        "typedef struct hcu_raw_collision_shared_edge_golden {",
        "    int map_id, bsp_index;",
        "    int surface_index[2], material_index[2], plane_designator[2];",
        "    int flags[2], breakable_index[2];",
        "    int start_leaf[2], precontact_leaf[2], end_leaf[2];",
        "    float start[2][3], vector[2][3], t[2], point[2][3];",
        "} hcu_raw_collision_shared_edge_golden;",
        "static const hcu_raw_collision_shared_edge_golden "
        "hcu_raw_collision_shared_edge_goldens[] = {",
    ])
    for map_id, bsp_index, cases in shared_edge_rows:
        initializer = f"{map_id}, {bsp_index}"
        for key in ("surface_index", "material_index", "plane_designator",
                    "flags", "breakable_index", "start_leaf",
                    "precontact_leaf", "end_leaf"):
            initializer += ", {" + ", ".join(
                str(case[key]) for case in cases) + "}"
        for key in ("start", "vector"):
            initializer += ", {" + ", ".join(
                "{" + ", ".join(f(value) for value in case[key]) + "}"
                for case in cases) + "}"
        initializer += ", {" + ", ".join(
            f(case["t"]) for case in cases) + "}"
        initializer += ", {" + ", ".join(
            "{" + ", ".join(f(value) for value in case["point"]) + "}"
            for case in cases) + "}"
        lines.append("    {" + initializer + "},")
    lines.extend([
        "};",
        "#define HCU_RAW_COLLISION_SHARED_EDGE_GOLDEN_COUNT "
        "(sizeof(hcu_raw_collision_shared_edge_goldens) / "
        "sizeof(hcu_raw_collision_shared_edge_goldens[0]))",
        "typedef struct hcu_raw_collision_flagged_golden {",
        "    int map_id, bsp_index, kind, surface_index, material_index;",
        "    int plane_designator, flags, breakable_index;",
        "    int surface_group_count, surface_group[4];",
        "    int start_leaf, precontact_leaf, end_leaf;",
        "    float start[3], vector[3], t, point[3];",
        "} hcu_raw_collision_flagged_golden;",
        "static const hcu_raw_collision_flagged_golden "
        "hcu_raw_collision_flagged_goldens[] = {",
    ])
    for map_id, bsp_index, kind, case in flagged_rows:
        fields = [map_id, bsp_index, kind, case["surface_index"],
                  case["material_index"], case["plane_designator"],
                  case["flags"], case["breakable_index"]]
        group = case.get("surface_group", [case["surface_index"]])
        if not 1 <= len(group) <= 4:
            raise AssertionError("flagged collision surface group exceeds fixture bounds")
        fields += [len(group)]
        fields += list(group) + [-1] * (4 - len(group))
        fields += [case["start_leaf"], case["precontact_leaf"], case["end_leaf"]]
        initializer = ", ".join(str(value) for value in fields)
        arrays = [case["start"], case["vector"], (case["t"],), case["point"]]
        initializer += ", " + ", ".join(
            "{" + ", ".join(f(value) for value in values) + "}"
            for values in arrays)
        lines.append("    {" + initializer + "},")
    lines.extend([
        "};",
        "#define HCU_RAW_COLLISION_FLAGGED_GOLDEN_COUNT "
        "(sizeof(hcu_raw_collision_flagged_goldens) / "
        "sizeof(hcu_raw_collision_flagged_goldens[0]))",
        "",
    ])
    path.write_text("\n".join(lines))


def write_player_pvs_golden_header(path, rows):
    """Write raw-Xbox-derived aggregate PVS vectors for CE's host fixture."""
    lines = [
        "typedef struct hcu_raw_player_pvs_golden {",
        "    int map_id, bsp_index, cluster_count;",
        "    short player_clusters[4];",
        "    short root_cluster;",
        "    unsigned long expected_all[16];",
        "    unsigned long expected_local[16];",
        "    unsigned long expected_root_all[16];",
        "    unsigned long expected_root_local[16];",
        "} hcu_raw_player_pvs_golden;",
        "static const hcu_raw_player_pvs_golden hcu_raw_player_pvs_goldens[] = {",
    ]
    for map_id, rows_for_map in rows:
        for row in rows_for_map:
            clusters = ", ".join(str(value) for value in row["player_clusters"])
            all_words = ", ".join(f"0x{value:08X}UL" for value in row["expected_all"])
            local_words = ", ".join(f"0x{value:08X}UL" for value in row["expected_local"])
            root_all_words = ", ".join(
                f"0x{value:08X}UL" for value in row["expected_root_all"])
            root_local_words = ", ".join(
                f"0x{value:08X}UL" for value in row["expected_root_local"])
            lines.append(
                f"    {{{map_id}, {row['bsp_index']}, {row['clusters']}, "
                f"{{{clusters}}}, {row['root_cluster']}, "
                f"{{{all_words}}}, {{{local_words}}}, "
                f"{{{root_all_words}}}, {{{root_local_words}}}}},")
    lines.extend([
        "};",
        "#define HCU_RAW_PLAYER_PVS_GOLDEN_COUNT "
        "(sizeof(hcu_raw_player_pvs_goldens) / sizeof(hcu_raw_player_pvs_goldens[0]))",
        "",
    ])
    path.write_text("\n".join(lines))


def write_sound_pas_golden_header(path, rows):
    """Write raw-Xbox-derived listener/PAS rows for the CE sound fixture."""
    lines = [
        "typedef struct hcu_raw_sound_pas_golden {",
        "    int map_id, bsp_index, cluster_count;",
        "    int union_proved;",
        "    short listener_clusters[3];",
        "    unsigned long expected_words[16];",
        "} hcu_raw_sound_pas_golden;",
        "static const hcu_raw_sound_pas_golden hcu_raw_sound_pas_goldens[] = {",
    ]
    for map_id, rows_for_map in rows:
        for row in rows_for_map:
            clusters = ", ".join(str(value) for value in row["listener_clusters"])
            words = ", ".join(f"0x{value:08X}UL" for value in row["words"])
            lines.append(
                f"    {{{map_id}, {row['bsp_index']}, {row['clusters']}, "
                f"{row['union_proved']}, "
                f"{{{clusters}}}, {{{words}}}}},")
    lines.extend([
        "};",
        "#define HCU_RAW_SOUND_PAS_GOLDEN_COUNT "
        "(sizeof(hcu_raw_sound_pas_goldens) / sizeof(hcu_raw_sound_pas_goldens[0]))",
        "",
    ])
    path.write_text("\n".join(lines))


def write_fog_plane_golden_header(path, rows, none_rows=()):
    none_count = sum(len(rows_for_map) for _map_id, rows_for_map in none_rows)
    lines = [
        "typedef struct hcu_raw_fog_plane_golden {",
        "    int map_id, bsp_index, cluster_index, reference, plane_index;",
        "    int region_index, fog_palette_index, fog_datum;",
        "    int region_weather, cluster_weather, weather;",
        "    float plane[4];",
        "} hcu_raw_fog_plane_golden;",
        "static const hcu_raw_fog_plane_golden hcu_raw_fog_plane_goldens[] = {",
    ]
    for map_id, rows_for_map in rows:
        for row in rows_for_map:
            def c_float(value):
                text = f"{value:.9g}"
                if "." not in text and "e" not in text.lower():
                    text += ".0"
                return text + "f"
            plane = ", ".join(c_float(value) for value in row["plane"])
            lines.append(
                f"    {{{map_id}, {row['bsp_index']}, {row['cluster_index']}, "
                f"{row['reference']}, {row['plane_index']}, {row['region_index']}, "
                f"{row['fog_palette_index']}, {row['fog_datum']}, "
                f"{row['region_weather']}, {row['cluster_weather']}, "
                f"{row['weather']}, {{{plane}}}}},")
    lines.extend([
        "};",
        "#define HCU_RAW_FOG_PLANE_GOLDEN_COUNT "
        "(sizeof(hcu_raw_fog_plane_goldens) / sizeof(hcu_raw_fog_plane_goldens[0]))",
        "typedef struct hcu_raw_fog_none_golden {",
        "    int map_id, bsp_index, cluster_index, reference;",
        "} hcu_raw_fog_none_golden;",
        "static const hcu_raw_fog_none_golden hcu_raw_fog_none_goldens[] = {",
    ])
    for map_id, rows_for_map in none_rows:
        for row in rows_for_map:
            lines.append(
                f"    {{{map_id}, {row['bsp_index']}, {row['cluster_index']}, "
                f"{row['reference']}}},")
    if none_count == 0:
        lines.append("    {0, 0, 0, 0},")
    lines.extend([
        "};",
        ("#define HCU_RAW_FOG_NONE_GOLDEN_COUNT "
         "(sizeof(hcu_raw_fog_none_goldens) / sizeof(hcu_raw_fog_none_goldens[0]))")
        if none_count else "#define HCU_RAW_FOG_NONE_GOLDEN_COUNT 0u",
        "",
    ])
    path.write_text("\n".join(lines))


class RealCeScenarioBspSwitchTest(unittest.TestCase):
    def test_real_ce_switch_control_flow_and_global_publication(self):
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for the ILP32 CE scenario fixture")

        source = HCU / "source/scenario/scenario.c"
        prefix = ROOT / "tests/hcu_scenario_host32_prefix.h"
        shim = ROOT / "tests/hcu_scenario_host_shim"
        includes = [
            ROOT / "tests", shim,
            HCU / "port/ps2/include", HCU / "port/linux/game",
            HCU / "port/include", HCU / "source", HCU / "source/cseries",
            HCU / "source/scenario", HCU / "source/structures",
            HCU / "source/objects", HCU / "source/physics",
            HCU / "source/cache", HCU / "source/tag_files",
            HCU / "source/math", HCU / "source/sound", Path("/usr/include"),
        ]

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            semantics = temp / "halo_ps2_msvc_semantics.h"
            link_map = temp / "scenario-switch.map"
            executable = temp / "scenario-switch-test"
            subprocess.run([
                sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"),
                "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)

            command = [
                compiler, *host_abi32_flags(), "-fshort-wchar", "-std=gnu89",
                "-fms-extensions", "-fcommon", "-fwrapv", "-ffunction-sections",
                "-fdata-sections", "-fno-strict-aliasing",
                "-fno-delete-null-pointer-checks", "-include", str(prefix),
                "-include", str(semantics), "-w",
            ]
            command.extend("-I" + str(path) for path in includes)
            command.extend([
                "-Wl,--gc-sections", "-Wl,-u,scenario_switch_structure_bsp",
                "-Wl,-Map=" + str(link_map),
                str(ROOT / "tests/hcu_scenario_bsp_switch_main.c"), str(source),
                "-o", str(executable),
            ])
            compile_result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            map_text = link_map.read_text()
            self.assertIn("scenario_switch_structure_bsp", map_text)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.strip(),
                             "real-ce-load-unload-switch branches=8 status=passed")

    def test_retail_ctag_and_cbsp_flow_through_ce_transaction_and_ps2_cache(self):
        """Run CE's switch/load lifecycle over two audited retail packages."""
        package_root_text = os.environ.get("HALO_HCU_M2_PACKAGE_ROOT")
        manifest_text = os.environ.get("HALO_HCU_M2_PACKAGE_MANIFEST")
        if not package_root_text or not manifest_text:
            self.skipTest("set the audited HCU M2 package root/manifest for a30 transaction inputs")
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for the ILP32 CE/PS2 cache fixture")

        sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
        from halo2ps2 import hp2
        from tools import ctag
        from tools.hmap import decode as decode_hmap
        from tools.cbsp import (
            HEADER as CBSP_HEADER,
            CbspError,
            decode as decode_cbsp,
            decode_catalog,
        )
        manifest = json.loads(Path(manifest_text).read_text())
        package_inputs = []
        package_rows = {item["map"]: item for item in manifest["maps"]}
        direct_only = os.environ.get("HALO_HCU_M2_DIRECT_CBSP_ONLY") == "1"
        for map_name in (("a50",) if direct_only else ("a30", "a50")):
            package_path = Path(package_root_text) / f"{map_name}.hp2"
            if not package_path.is_file():
                self.skipTest(f"audited {map_name}.hp2 package is missing: {package_path}")
            row = package_rows[map_name]
            source_map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
            if not source_map_path.is_file():
                self.skipTest(f"decompressed {map_name} source map is missing: {source_map_path}")
            self.assertEqual(hashlib.sha256(source_map_path.read_bytes()).hexdigest(),
                             row["source_sha256"])
            package_bytes = package_path.read_bytes()
            self.assertEqual(hashlib.sha256(package_bytes).hexdigest(), row["package_sha256"])
            package = hp2.parse(package_bytes)
            identity = decode_hmap(package.read("HMAP"))
            self.assertEqual(identity.source_sha256.hex(), row["source_sha256"])
            ctag.decode(package.read("CTAG"), max_image_size=16 * 1024 * 1024)
            entries = decode_catalog(package.read("CBIX"),
                                     expected_file_length=identity.file_length)
            self.assertEqual(len(entries), row["bsp_count"])
            self.assertEqual(tuple(entry.section_tag for entry in entries),
                             tuple(f"B{index:03d}" for index in range(len(entries))))
            cbsp_payloads = [package.read(entry.section_tag) for entry in entries]
            for entry, payload in zip(entries, cbsp_payloads):
                decoded = decode_cbsp(payload, max_image_size=8 * 1024 * 1024)
                self.assertEqual((decoded.source_file_offset, decoded.source_file_size),
                                 (entry.file_offset, entry.file_size))
            source_pvs_pairs = retail_source_pvs_pair_oracle(
                source_map_path, len(entries))
            source_player_pvs = retail_source_player_pvs_oracle(
                source_map_path, len(entries))
            source_sound_pas = retail_source_sound_pas_oracle(
                source_map_path, len(entries))
            source_fog_planes = retail_source_fog_plane_oracle(
                source_map_path, len(entries))
            collision_goldens = retail_source_collision_goldens(
                source_map_path, len(entries))
            package_inputs.append((map_name, package_path, source_map_path,
                                   identity, entries, source_pvs_pairs,
                                   collision_goldens, source_player_pvs,
                                   source_sound_pas, source_fog_planes))

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            semantics = temp / "halo_ps2_msvc_semantics.h"
            link_map = temp / "retail-ce-transaction.map"
            executable = temp / "retail-ce-transaction"
            write_collision_golden_header(
                temp / "hcu_collision_golden.h",
                [(30 if item[0] == "a30" else 50, item[6])
                 for item in package_inputs])
            write_player_pvs_golden_header(
                temp / "hcu_player_pvs_golden.h",
                [(30 if item[0] == "a30" else 50, item[7])
                 for item in package_inputs])
            write_sound_pas_golden_header(
                temp / "hcu_sound_pas_golden.h",
                [(30 if item[0] == "a30" else 50, item[8])
                 for item in package_inputs])
            write_fog_plane_golden_header(
                temp / "hcu_fog_plane_golden.h",
                [(30 if item[0] == "a30" else 50, item[9])
                 for item in package_inputs])
            subprocess.run([
                sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"),
                "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)
            includes = [
                temp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                HCU / "port/ps2/include", HCU / "port/linux/game",
                HCU / "port/include", HCU / "source", HCU / "source/cseries",
                HCU / "source/scenario", HCU / "source/structures",
                HCU / "source/memory", HCU / "source/game",
                HCU / "source/input",
                HCU / "source/cache", HCU / "source/tag_files",
                HCU / "source/objects", HCU / "source/physics",
                HCU / "source/math", HCU / "source/sound",
                ROOT / "src", ROOT / "submodules/halo-ps2/engine/src",
                ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim",
                Path("/usr/include"),
            ]
            command = [
                compiler, *host_abi32_flags(), "-fshort-wchar", "-std=gnu99",
                "-fms-extensions", "-fcommon", "-fwrapv", "-ffunction-sections",
                "-fdata-sections", "-fno-strict-aliasing",
                "-fno-delete-null-pointer-checks", "-DHCU_BSP_RETAIL_INTEGRATION=1",
                "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                "-include", str(semantics), "-w",
            ]
            command.extend("-I" + str(path) for path in includes)
            port = HCU / "port/ps2"
            schema = HCU / "port/linux/game"
            command.extend([
                "-Wl,--gc-sections", "-Wl,-u,scenario_switch_structure_bsp",
                "-Wl,-u,scenario_get_sound_environment",
                "-Wl,-u,hcu_test_players_compute_combined_pvs",
                "-Wl,--wrap=read",
                "-Wl,-Map=" + str(link_map),
                str(ROOT / "tests/hcu_scenario_bsp_switch_main.c"),
                str(ROOT / "tests/hcu_game_sound_host32.c"),
                str(ROOT / "tests/hcu_player_pvs_host32.c"),
                str(ROOT / "tests/hcu_objects_host32.c"),
                str(ROOT / "tests/hcu_real_math_host32.c"),
                str(ROOT / "tests/hcu_map_service_visit_test_bridge.c"),
                str(HCU / "source/scenario/scenario.c"),
                str(HCU / "source/sound/sound_environment_definitions.c"),
                str(HCU / "source/memory/data.c"),
                str(HCU / "source/math/integer_math.c"),
                str(HCU / "source/physics/collisions.c"),
                str(HCU / "source/physics/collision_bsp.c"),
                str(ROOT / "tests/hcu_bsp3d_host32.c"),
                str(HCU / "source/physics/bsp2d.c"),
                str(port / "src/ps2_cache.c"), str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"),
                str(schema / "tag_schema_groups.c"),
                str(schema / "tag_schema_collision.c"),
                str(schema / "tag_schema_models.c"),
                str(schema / "tag_schema_objects.c"),
                str(schema / "tag_schema_render.c"),
                str(schema / "tag_schema_effects.c"),
                str(schema / "tag_schema_scenario.c"),
                str(ROOT / "src/stream/ctag_mount.c"),
                str(ROOT / "src/stream/ctag_map_source.c"),
                str(ROOT / "src/stream/ctag_ps2_backend.c"),
                str(ROOT / "src/stream/cbsp_catalog.c"),
                str(ROOT / "src/stream/ctag_resource_index.c"),
                str(ROOT / "src/stream/hmap.c"),
                str(ROOT / "src/stream/sha256.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/file.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/world/section.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/core/mem.c"),
                "-o", str(executable),
            ])
            compile_result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            if os.environ.get("HALO_HCU_M2_RETAIN_LINK_ARTIFACTS") == "1":
                retained = ROOT / "build/m2-group-d-file-backed-transaction"
                retained.mkdir(parents=True, exist_ok=True)
                shutil.copy2(executable, retained / "retail-ce-transaction")
                shutil.copy2(link_map, retained / "retail-ce-transaction.map")
                shutil.copy2(temp / "hcu_collision_golden.h",
                             retained / "hcu_collision_golden.h")
                shutil.copy2(temp / "hcu_player_pvs_golden.h",
                             retained / "hcu_player_pvs_golden.h")
                shutil.copy2(temp / "hcu_sound_pas_golden.h",
                             retained / "hcu_sound_pas_golden.h")
                shutil.copy2(temp / "hcu_fog_plane_golden.h",
                             retained / "hcu_fog_plane_golden.h")
            map_text = link_map.read_text()
            for symbol in ("scenario_switch_structure_bsp", "scenario_structure_bsp_load",
                           "scenario_structure_bsp_unload", "ps2_ctag_materialize",
                           "ps2_cbsp_materialize", "cache_file_read",
                           "ctag_mount_hp2_file_verified_discover_with_bsp_catalog",
                           "ctag_map_source_read", "world_load_section_with_scratch",
                           "file_reader_open", "hp2_load_stream", "load_bsp_extent",
                           "ctag_ps2_cache_backend", "cbsp_catalog_find",
                           "hp2_open_header", "hp2_find", "ctag_resource_index_read"):
                self.assertIn(symbol, map_text)
            for symbol in ("collision_test_vector", "collision_bsp_test_vector",
                           "object_test_vector", "retail_fixture_forbid_object_path",
                           "compute_sound_obstruction", "hcu_test_compute_sound_obstruction"):
                self.assertIn(symbol, map_text,
                              f"retained collision-wrapper closure lacks {symbol}")
            self.assertIn("scenario_location_underwater", map_text,
                          "retail transaction does not retain CE's location/weather consumer")
            self.assertIn("scenario_get_fog_region_index", map_text,
                          "retail transaction does not retain CE's fog-plane lookup")
            self.assertIn("scenario_location_water_depth", map_text,
                          "retail transaction does not retain CE's water-depth consumer")
            self.assertIn("scenario_get_sound_environment", map_text,
                          "retail transaction does not retain CE's listener environment consumer")
            for symbol in ("hcu_test_compute_combined_pas", "compute_combined_pas",
                           "location_potentially_audible",
                           "structure_bsp_get_cluster_encoded_sound_distance"):
                self.assertIn(symbol, map_text,
                              f"CE sound PAS consumer closure lacks {symbol}")
            for symbol in ("players_compute_combined_pvs",
                           "hcu_test_players_compute_combined_pvs",
                           "data_iterator_new", "data_iterator_next",
                           "structure_bsp_get_cluster_pvs", "bit_vector_or"):
                self.assertIn(symbol, map_text,
                              f"player-PVS consumer closure lacks {symbol}")
            for symbol in ("object_get_ultimate_parent", "object_get_and_verify_type",
                           "datum_get"):
                self.assertIn(symbol, map_text,
                              f"live CE player-root PVS closure lacks {symbol}")
            self.assertIn("hcu_map_service_test_visit_section", map_text)
            self.assertIn("world_visit_section_with_scratch", map_text)
            for (map_name, package_path, source_map_path, identity, entries,
                 source_pvs_pairs, collision_goldens,
                 source_player_pvs, source_sound_pas, source_fog_planes) in package_inputs:
                if direct_only:
                    break
                with self.subTest(map=map_name):
                    original_package = package_path.read_bytes()
                    package = hp2.parse(original_package)
                    cbix_index = package.sections.index(package.find("CBIX"))
                    corrupt_crc_offset = hp2.HEADER_SIZE + cbix_index * hp2.ENTRY_SIZE + 20
                    corrupt_package = bytearray(original_package)
                    corrupt_package[corrupt_crc_offset] ^= 1
                    corrupt_package_path = temp / f"{map_name}-bad-cbix-crc.hp2"
                    corrupt_package_path.write_bytes(corrupt_package)
                    args = [
                        str(executable), str(package_path), map_name,
                        str(source_map_path), str(identity.file_length),
                        str(identity.tag_data_offset), str(identity.tag_data_size),
                        str(corrupt_package_path), str(len(entries)),
                    ]
                    for entry in entries:
                        args.extend((str(entry.file_offset), str(entry.file_size)))
                    run = subprocess.run(args, capture_output=True, text=True)
                    if run.returncode in (-31, 159):
                        self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    expected_map_id = 30 if map_name == "a30" else 50
                    sound_environment_rows = [tuple(map(int, row)) for row in re.findall(
                        r"^sound-environment map=(\d+) bsp=(\d+) cluster=(\d+) "
                        r"palette=(-?\d+) tag=(-?\d+) background=(-?\d+) "
                        r"boundary=(\d+) status=passed$", run.stdout, re.MULTILINE)]
                    self.assertTrue(sound_environment_rows,
                                    "package transaction never exercised CE's listener environment selector")
                    self.assertTrue(all(row[0] == expected_map_id
                                        for row in sound_environment_rows))
                    sound_oracle = retail_source_sound_environment_oracle(
                        source_map_path, len(entries))
                    observed_sound_by_bsp = {}
                    for (map_id, bsp_index, cluster_index, palette_index,
                         environment_tag, background_tag, boundary) in sound_environment_rows:
                        expected = sound_oracle.get(bsp_index)
                        self.assertIsNotNone(
                            expected,
                            f"CE queried a source BSP without a fog-free palette candidate: {map_name}/{bsp_index}")
                        actual = (cluster_index, palette_index, environment_tag,
                                  background_tag, boundary)
                        wanted = (expected["cluster_index"], expected["palette_index"],
                                  expected["environment_tag"], expected["background_tag"], 0)
                        self.assertEqual(actual, wanted,
                                         f"CE sound palette differs from raw BSP oracle: {map_name}/{expected['path']}")
                        observed_sound_by_bsp.setdefault(bsp_index, actual)
                    self.assertEqual(set(observed_sound_by_bsp), set(sound_oracle),
                                     "sound-environment palette consumer was not exercised on every source BSP candidate")
                    sound_pas_rows = [tuple(map(int, match)) for match in re.findall(
                        r"^sound-pas map=(\d+) bsp=(\d+) clusters=(\d+) "
                        r"listeners=(-?\d+),(-?\d+),(-?\d+) union=(\d+) "
                        r"words=16 none=0 status=passed$",
                        run.stdout, re.MULTILINE)]
                    self.assertTrue(sound_pas_rows,
                                    "CE combined-PAS consumer was not exercised")
                    sound_pas_by_bsp = {}
                    for (pas_map_id, bsp_index, cluster_count, listener_a,
                         listener_b, none_listener, union_proved) in sound_pas_rows:
                        self.assertEqual(pas_map_id, expected_map_id)
                        sound_pas_by_bsp[bsp_index] = (
                            cluster_count, listener_a, listener_b, none_listener,
                            union_proved)
                    self.assertEqual(set(sound_pas_by_bsp), set(range(len(entries))),
                                     "CE combined-PAS query missed a published BSP")
                    for oracle in source_sound_pas:
                        self.assertEqual(
                            sound_pas_by_bsp[oracle["bsp_index"]],
                            (oracle["clusters"], *oracle["listener_clusters"],
                             oracle["union_proved"]),
                            f"combined PAS listener selection changed for "
                            f"{map_name}/{oracle['path']}")
                    self.assertTrue(any(row[-1] for row in sound_pas_by_bsp.values()),
                                    "no source BSP proved a two-listener PAS union")
                    fog_rows = [tuple(map(int, match)) for match in re.findall(
                        r"^fog-plane map=(\d+) bsp=(\d+) cluster=(\d+) "
                        r"reference=(-?\d+) plane=(\d+) region=(\d+) "
                        r"fog=(-?\d+) weather=(-?\d+) underwater=(\d+) "
                        r"status=passed$", run.stdout, re.MULTILINE)]
                    self.assertEqual(bool(fog_rows), bool(source_fog_planes),
                                     "CE fog-plane query presence differs from raw BSP candidates")
                    source_fog_by_bsp = {
                        row["bsp_index"]: (
                            row["cluster_index"], row["reference"],
                            row["plane_index"], row["region_index"],
                            row["fog_datum"], row["weather"])
                        for row in source_fog_planes
                    }
                    observed_fog = set()
                    for (fog_map_id, bsp_index, cluster_index, reference,
                         plane_index, region_index, fog_datum, weather,
                         underwater) in fog_rows:
                        self.assertEqual(fog_map_id, expected_map_id)
                        self.assertIn(underwater, (0, 1))
                        actual = (
                            cluster_index, reference, plane_index, region_index,
                            fog_datum, weather)
                        self.assertEqual(actual, source_fog_by_bsp.get(bsp_index),
                                         "CE fog plane/region/tag/weather differs from raw BSP")
                        observed_fog.add(bsp_index)
                    self.assertEqual(observed_fog, set(source_fog_by_bsp),
                                     "CE fog-plane consumer missed a source BSP candidate")
                    player_pvs_rows = [tuple(map(int, match)) for match in re.findall(
                        r"^player-pvs map=(\d+) bsp=(\d+) clusters=(\d+) "
                        r"words=16 root-refresh=(\d+) root-none-fallback=1 "
                        r"idempotent=1 status=passed$",
                        run.stdout, re.MULTILINE)]
                    expected_map_id = 30 if map_name == "a30" else 50
                    player_pvs_by_bsp = {
                        bsp_index: (cluster_count, root_cluster)
                        for map_id, bsp_index, cluster_count, root_cluster in player_pvs_rows
                        if map_id == expected_map_id
                    }
                    self.assertEqual(set(player_pvs_by_bsp),
                                     set(range(len(entries))),
                                     "CE player-PVS consumer did not query each published BSP")
                    for oracle in source_player_pvs:
                        self.assertEqual(player_pvs_by_bsp[oracle["bsp_index"]],
                                         (oracle["clusters"], oracle["root_cluster"]),
                                         f"player-PVS cluster count changed for "
                                         f"{map_name}/{oracle['path']}")
                    pvs_rows = [tuple(map(int, match)) for match in re.findall(
                        r"^pvs-pair bsp=(\d+) clusters=(\d+) visible=(\d+),(\d+) "
                        r"hidden=(\d+),(\d+)$", run.stdout, re.MULTILINE)]
                    self.assertTrue(pvs_rows, "CE fixture emitted no PVS pair observations")
                    observed_bsp_indices = set()
                    for bsp_index, clusters, vis_from, vis_to, hid_from, hid_to in pvs_rows:
                        self.assertLess(bsp_index, len(source_pvs_pairs))
                        oracle = source_pvs_pairs[bsp_index]
                        self.assertEqual(clusters, oracle["clusters"],
                                         f"cluster count changed for {map_name}/{oracle['path']}")
                        self.assertEqual((vis_from, vis_to), oracle["visible"],
                                         f"visible PVS pair changed for {map_name}/{oracle['path']}")
                        self.assertEqual((hid_from, hid_to), oracle["hidden"],
                                         f"hidden PVS pair changed for {map_name}/{oracle['path']}")
                        observed_bsp_indices.add(bsp_index)
                    self.assertEqual(observed_bsp_indices, set(range(len(entries))))
                    sound_rows = [
                        (int(bsp), case, int(source), int(target), int(raw), int(pvs),
                         float(obstruction), float(occlusion))
                        for bsp, case, source, target, raw, pvs, obstruction, occlusion
                        in re.findall(
                            r"^sound-obstruction bsp=(\d+) case=(missing|unreachable|hidden) "
                            r"from=(-?\d+) to=(-?\d+) raw=(-?\d+) pvs=(-?\d+) "
                            r"distance=10 obstruction=([-+0-9.eE]+) "
                            r"occlusion=([-+0-9.eE]+)$", run.stdout, re.MULTILINE)]
                    sound_bsp_indices = set()
                    observed_cases = {}
                    for bsp_index, case, source, target, raw, pvs, obstruction, occlusion in sound_rows:
                        self.assertLess(bsp_index, len(source_pvs_pairs))
                        oracle = source_pvs_pairs[bsp_index]
                        sound_bsp_indices.add(bsp_index)
                        observed_cases.setdefault(bsp_index, set()).add(case)
                        if case == "missing":
                            self.assertEqual((source, target, raw, pvs), (-1, 0, -1, -1))
                            self.assertAlmostEqual(obstruction, 0.6, delta=1e-6)
                            self.assertAlmostEqual(occlusion, 1.0, delta=1e-6)
                        elif case == "unreachable":
                            expected = oracle["unreachable"]
                            self.assertIsNotNone(expected,
                                f"fixture emitted unavailable sentinel case for {map_name}/{oracle['path']}")
                            self.assertEqual((source, target, raw, pvs), expected)
                            self.assertEqual(raw, 0xFF)
                            self.assertAlmostEqual(obstruction, 0.6, delta=1e-6)
                            self.assertAlmostEqual(occlusion, 1.0, delta=1e-6)
                        else:
                            expected_pair = oracle["hidden_reachable"]
                            self.assertIsNotNone(expected_pair,
                                f"fixture emitted unavailable hidden case for {map_name}/{oracle['path']}")
                            expected_source, expected_target, expected_raw = expected_pair
                            self.assertEqual((source, target, raw, pvs),
                                             (expected_source, expected_target, expected_raw, 0))
                            cluster_distance = (raw & 0x7F) * (256.0 / 127.0)
                            self.assertLess(cluster_distance, 256.0)
                            expected_occlusion = max(0.0, min(1.0,
                                (1.0 - 10.0 / (cluster_distance + 10.0)) * 1.4))
                            self.assertAlmostEqual(obstruction, 0.6, delta=1e-6)
                            self.assertAlmostEqual(occlusion, expected_occlusion, delta=1e-5)
                    self.assertEqual(sound_bsp_indices, set(range(len(entries))))
                    for bsp_index in sound_bsp_indices:
                        oracle = source_pvs_pairs[bsp_index]
                        cases = observed_cases[bsp_index]
                        self.assertIn("missing", cases)
                        self.assertEqual("unreachable" in cases,
                                         oracle["unreachable"] is not None)
                        self.assertEqual("hidden" in cases,
                                         oracle["hidden_reachable"] is not None)
                    underwater_rows = [tuple(map(int, match)) for match in re.findall(
                        r"^underwater-weather bsp=(\d+) cluster=(\d+) fog=-1 "
                        r"weather=(-?\d+) result=(\d+)$", run.stdout, re.MULTILINE)]
                    observed_underwater = {}
                    for bsp_index, cluster_index, weather_index, underwater in underwater_rows:
                        self.assertLess(bsp_index, len(source_pvs_pairs))
                        oracle = source_pvs_pairs[bsp_index]
                        expected = oracle["underwater_weather"]
                        self.assertIsNotNone(expected,
                            f"source BSP has no unfogged cluster: {map_name}/{oracle['path']}")
                        expected_cluster, _raw_weather, expected_weather = expected
                        self.assertEqual((cluster_index, underwater),
                                         (expected_cluster, 0))
                        self.assertEqual(weather_index, expected_weather,
                            f"CE weather palette differs for {map_name}/{oracle['path']}")
                        if bsp_index in observed_underwater:
                            self.assertEqual(observed_underwater[bsp_index], cluster_index,
                                "repeated BSP publication changed CE weather query selection")
                        observed_underwater[bsp_index] = cluster_index
                    self.assertEqual(set(observed_underwater), set(range(len(entries))))
                    collision_rows = [
                        (int(map_id), int(bsp), int(surface), int(material),
                         int(material_type), int(leaf), int(cluster), float(t),
                         tuple(map(float, point.split(","))))
                        for map_id, bsp, surface, material, material_type, leaf,
                            cluster, t, point in re.findall(
                                r"^collision-golden map=(\d+) bsp=(\d+) surface=(\d+) "
                                r"material=(\d+) type=(\d+) leaf=(\d+) cluster=(\d+) "
                                r"t=([-+0-9.eE]+) point=([-+0-9.eE]+,[-+0-9.eE]+,[-+0-9.eE]+)$",
                                run.stdout, re.MULTILINE)]
                    expected_map_id = 30 if map_name == "a30" else 50
                    expected_by_bsp = {row["bsp_index"]: row
                                       for row in collision_goldens}
                    observed_collision_bsps = set()
                    for (map_id, bsp_index, surface_index, material_index,
                         material_type, leaf_index, cluster_index, t, point) in collision_rows:
                        self.assertEqual(map_id, expected_map_id)
                        self.assertIn(bsp_index, expected_by_bsp)
                        oracle = expected_by_bsp[bsp_index]
                        self.assertEqual((surface_index, material_index,
                                          material_type, leaf_index, cluster_index),
                                         (oracle["surface_index"], oracle["material_index"],
                                          oracle["material_type"], oracle["leaf_index"],
                                          oracle["cluster_index"]))
                        self.assertAlmostEqual(t, oracle["t"], delta=0.0001)
                        for actual, expected in zip(point, oracle["point"]):
                            self.assertAlmostEqual(actual, expected, delta=0.0001)
                        observed_collision_bsps.add(bsp_index)
                    self.assertEqual(observed_collision_bsps, set(range(len(entries))),
                                     "raw-source collision golden did not run per retail BSP")
                    if map_name == "a30":
                        edge_tie = re.search(
                            r"^collision-edge-pair map=30 bsp=0 surfaces=27,94 "
                            r"epsilon=0\.01 tie-surface=(\d+) status=passed$",
                            run.stdout, re.MULTILINE)
                        self.assertIsNotNone(edge_tie)
                        self.assertIn(int(edge_tie.group(1)), (27, 94))
                    else:
                        self.assertNotIn("collision-edge-pair", run.stdout)
                    self.assertIn(f"{corrupt_package_path}: decoding CBIX failed (8)", run.stdout)
                    self.assertEqual(run.stdout.strip().splitlines()[-1],
                        f"retail-ce-ps2-bsp-transaction map={map_name} refs={len(entries)} "
                        f"selections={len(entries) + 17} bsp-sections={len(entries) + 14} "
                        f"cluster-query-bsp={len(entries) + 1} "
                        f"collision-query-bsp={len(entries) + 1} status=passed")

            # Exercise the exact production HCU section-visitor adapter and
            # PS2 cache callback inside CE's real a50 BSP-switch transaction.
            # This test-only low-level mount bypass does not change the normal
            # UI-only hcu_map_service_preflight policy.
            map_name = "a50"
            package_path = Path(package_root_text) / "a50.hp2"
            source_map_path = ROOT / "build/retail-maps/decompressed/a50.map"
            row = package_rows[map_name]
            self.assertEqual(hashlib.sha256(original_package := package_path.read_bytes()).hexdigest(),
                             row["package_sha256"])
            self.assertEqual(hashlib.sha256(source_map_path.read_bytes()).hexdigest(),
                             row["source_sha256"])
            identity = decode_hmap(hp2.parse(package_path.read_bytes()).read("HMAP"))
            entries = decode_catalog(hp2.parse(package_path.read_bytes()).read("CBIX"),
                                     expected_file_length=identity.file_length)
            parsed_original = hp2.parse(original_package)

            bad_b001 = bytearray(original_package)
            b001_index = parsed_original.sections.index(parsed_original.find("B001"))
            b001_crc_offset = hp2.HEADER_SIZE + b001_index * hp2.ENTRY_SIZE + 20
            bad_b001[b001_crc_offset] ^= 1
            bad_b001_path = temp / "a50-bad-b001-outer-crc.hp2"
            bad_b001_path.write_bytes(bad_b001)
            with self.assertRaises(hp2.Hp2Error):
                hp2.parse(bad_b001).read("B001")

            bad_cbix = bytearray(original_package)
            cbix_index = parsed_original.sections.index(parsed_original.find("CBIX"))
            cbix_crc_offset = hp2.HEADER_SIZE + cbix_index * hp2.ENTRY_SIZE + 20
            bad_cbix[cbix_crc_offset] ^= 1
            bad_cbix_path = temp / "a50-bad-cbix-crc-for-direct-visitor.hp2"
            bad_cbix_path.write_bytes(bad_cbix)
            direct_args = [
                str(executable), str(bad_b001_path), map_name,
                str(source_map_path), str(identity.file_length),
                str(identity.tag_data_offset), str(identity.tag_data_size),
                str(bad_cbix_path), str(len(entries)),
            ]
            for entry in entries:
                direct_args.extend((str(entry.file_offset), str(entry.file_size)))
            direct_args.extend((str(package_path), "--direct-cbsp"))
            direct_run = subprocess.run(direct_args, capture_output=True, text=True)
            if direct_run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(direct_run.returncode, 0,
                             direct_run.stdout[-1200:] + direct_run.stderr[-1200:])
            self.assertIn("test-only capacity bypass: mounted a50 fixture directly;",
                          direct_run.stdout)
            self.assertIn("retail-ce-ps2-bsp-transaction map=a50", direct_run.stdout)
            self.assertEqual(direct_run.stdout.strip().splitlines()[-1],
                f"retail-ce-ps2-bsp-transaction map=a50 refs={len(entries)} "
                f"selections={len(entries) + 17} bsp-sections={len(entries) + 14} "
                f"cluster-query-bsp={len(entries) + 1} "
                f"collision-query-bsp={len(entries) + 1} status=passed")

            # Keep both HP2 and CBSP image checksums valid, but make one typed
            # CTAG-name relocation target one-past the actual tag image. The
            # production stream should reach the fixed BSP destination, pass
            # CBSP envelope/image/row validation, then fail specifically in
            # the PS2 in-place rebase before publishing CE's candidate BSP.
            bad_rebase_b001 = bytearray(parsed_original.read("B001"))
            (magic, version, image_size, relocation_count, table_offset,
             _image_crc, _source_offset, _source_size, _reserved) = \
                CBSP_HEADER.unpack_from(bad_rebase_b001)
            self.assertEqual(magic, b"CBSP")
            self.assertGreater(relocation_count, 0)
            target_field = None
            for relocation_index in range(relocation_count):
                row_offset = table_offset + relocation_index * 12
                if bad_rebase_b001[row_offset + 4] == 1:
                    target_field = int.from_bytes(
                        bad_rebase_b001[row_offset:row_offset + 4], "little")
                    bad_rebase_b001[row_offset + 8:row_offset + 12] = \
                        int(identity.tag_data_size).to_bytes(4, "little")
                    bad_rebase_b001[CBSP_HEADER.size + target_field:
                        CBSP_HEADER.size + target_field + 4] = \
                        int(identity.tag_data_size).to_bytes(4, "little")
                    break
            self.assertIsNotNone(target_field,
                                 "a50 B001 must contain a typed CTAG-name relocation")
            self.assertEqual(version, 1)
            self.assertEqual(table_offset, CBSP_HEADER.size + image_size)
            image_start = CBSP_HEADER.size
            image_end = image_start + image_size
            bad_rebase_b001[20:24] = (zlib.crc32(
                bad_rebase_b001[image_start:image_end]) & 0xFFFFFFFF).to_bytes(4, "little")
            bad_rebase_path = temp / "a50-bad-b001-relocation-target-valid-crcs.hp2"
            bad_rebase_path.write_bytes(hp2.build(parsed_original.name, [
                (section.tag,
                 bytes(bad_rebase_b001) if section.tag == "B001"
                 else parsed_original.read(section.tag))
                for section in parsed_original.sections
            ]))
            rebuilt_rebase_package = hp2.parse(bad_rebase_path.read_bytes())
            self.assertEqual(len(rebuilt_rebase_package.read("B001")),
                             len(bad_rebase_b001))
            relocation_args = [
                str(executable), str(bad_rebase_path), map_name,
                str(source_map_path), str(identity.file_length),
                str(identity.tag_data_offset), str(identity.tag_data_size),
                str(bad_cbix_path), str(len(entries)),
            ]
            for entry in entries:
                relocation_args.extend((str(entry.file_offset), str(entry.file_size)))
            relocation_args.extend((str(package_path), "--direct-cbsp-rebase"))
            relocation_run = subprocess.run(relocation_args, capture_output=True, text=True)
            if relocation_run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(relocation_run.returncode, 0,
                             relocation_run.stdout + relocation_run.stderr)
            self.assertIn("cbsp-stream reject=rebase", relocation_run.stdout)
            self.assertIn("test-only capacity bypass: mounted a50 fixture directly;",
                          relocation_run.stdout)
            self.assertEqual(relocation_run.stdout.strip().splitlines()[-1],
                f"retail-ce-ps2-bsp-transaction map=a50 refs={len(entries)} "
                f"selections={len(entries) + 17} bsp-sections={len(entries) + 14} "
                f"cluster-query-bsp={len(entries) + 1} "
                f"collision-query-bsp={len(entries) + 1} status=passed")

            # Keep the outer HP2 section valid while corrupting one byte in
            # the CBSP image. This forces the real visitor to finish and lets
            # the HCU cache parser—not HP2 CRC handling—reject the candidate.
            bad_cbsp_b001 = bytearray(parsed_original.read("B001"))
            self.assertGreater(len(bad_cbsp_b001), CBSP_HEADER.size)
            bad_cbsp_b001[CBSP_HEADER.size] ^= 1
            with self.assertRaises(CbspError):
                decode_cbsp(bytes(bad_cbsp_b001), max_image_size=8 * 1024 * 1024)
            inner_crc_sections = [
                (section.tag,
                 bytes(bad_cbsp_b001) if section.tag == "B001"
                 else parsed_original.read(section.tag))
                for section in parsed_original.sections
            ]
            bad_inner_crc_path = temp / "a50-bad-b001-inner-crc-valid-hp2.hp2"
            bad_inner_crc_path.write_bytes(
                hp2.build(parsed_original.name, inner_crc_sections))
            rebuilt_inner_package = hp2.parse(bad_inner_crc_path.read_bytes())
            # The enclosing section's CRC is freshly generated and valid.
            rebuilt_inner_package.read("B001")

            inner_crc_args = [
                str(executable), str(bad_inner_crc_path), map_name,
                str(source_map_path), str(identity.file_length),
                str(identity.tag_data_offset), str(identity.tag_data_size),
                str(bad_cbix_path), str(len(entries)),
            ]
            for entry in entries:
                inner_crc_args.extend((str(entry.file_offset), str(entry.file_size)))
            inner_crc_args.extend((str(package_path), "--direct-cbsp-inner-crc"))
            inner_crc_run = subprocess.run(inner_crc_args, capture_output=True, text=True)
            if inner_crc_run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(inner_crc_run.returncode, 0,
                             inner_crc_run.stdout + inner_crc_run.stderr)
            self.assertIn("cbsp-stream reject=validate", inner_crc_run.stdout)
            self.assertIn("test-only capacity bypass: mounted a50 fixture directly;",
                          inner_crc_run.stdout)
            self.assertEqual(inner_crc_run.stdout.strip().splitlines()[-1],
                f"retail-ce-ps2-bsp-transaction map=a50 refs={len(entries)} "
                f"selections={len(entries) + 17} bsp-sections={len(entries) + 14} "
                f"cluster-query-bsp={len(entries) + 1} "
                f"collision-query-bsp={len(entries) + 1} status=passed")


if __name__ == "__main__":
    unittest.main()
