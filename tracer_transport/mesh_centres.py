"""Read cell centres from the ASCII hexahedral OpenFOAM mesh."""
from pathlib import Path
import re
import numpy as np


def mesh_list(path):
    source = Path(path).read_text()
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    source = re.sub(r'//[^\n]*', '', source)
    body = re.split(r'FoamFile\s*\{.*?\}', source, maxsplit=1, flags=re.S)[-1].strip()
    match = re.fullmatch(r'(\d+)\s*\((.*)\)\s*', body, flags=re.S)
    if not match:
        raise ValueError(f'Invalid ASCII mesh list: {path}')
    return int(match[1]), match[2]


def cell_centres(mesh, count):
    mesh = Path(mesh)
    point_count, data = mesh_list(mesh/'points')
    points = np.array([np.fromstring(v, sep=' ') for v in re.findall(r'\(([^()]*)\)', data)])
    if points.shape != (point_count, 3):
        raise ValueError('Invalid mesh points')
    face_count, data = mesh_list(mesh/'faces')
    faces = re.findall(r'(\d+)\s*\(([^()]*)\)', data)
    if len(faces) != face_count or any(int(length) != 4 for length, _ in faces):
        raise ValueError('Expected quadrilateral hexahedral faces')
    indices = np.array([np.fromstring(v, sep=' ', dtype=int) for _, v in faces])
    if np.any(indices < 0) or np.any(indices >= point_count):
        raise ValueError('Face refers to an invalid point')
    face_centres = points[indices].mean(axis=1)
    owner_count, data = mesh_list(mesh/'owner')
    owner = np.fromstring(data, sep=' ', dtype=int)
    neighbour_count, data = mesh_list(mesh/'neighbour')
    neighbour = np.fromstring(data, sep=' ', dtype=int)
    if owner_count != face_count or len(owner) != owner_count or len(neighbour) != neighbour_count:
        raise ValueError('Invalid mesh owner/neighbour lists')
    if np.any(owner < 0) or np.any(owner >= count) or np.any(neighbour < 0) or np.any(neighbour >= count):
        raise ValueError('Face refers to an invalid cell')
    centres = np.zeros((count, 3))
    hits = np.zeros(count)
    np.add.at(centres, owner, face_centres)
    np.add.at(hits, owner, 1)
    np.add.at(centres, neighbour, face_centres[:neighbour_count])
    np.add.at(hits, neighbour, 1)
    if not np.all(hits == 6):
        raise ValueError('Expected six faces per cell')
    return centres/hits[:, None]
