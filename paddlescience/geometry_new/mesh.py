# Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import copy

import numpy as np
# import open3d
import pymesh
import pysdf
from stl import mesh as np_mesh
from typing import Union
# from ..data import PointBatchSampler, PointDataset
from .geometry import Geometry

# from typing import Tuple

# import pyvista
# from paddle.io import DataLoader



def area_of_triangles(v0: np.ndarray, v1: np.ndarray,
                      v2: np.ndarray) -> np.ndarray:
    """ref https://math.stackexchange.com/questions/128991/how-to-calculate-the-area-of-a-3d-triangle

    Args:
        v0 (np.ndarray): Coordinates of the first vertex of the triangle surface with shape of [N, 3].
        v1 (np.ndarray): Coordinates of the second vertex of the triangle surface with shape of [N, 3].
        v2 (np.ndarray): Coordinates of the third vertex of the triangle surface with shape of [N, 3].

    Returns:
        np.ndarray: Area of each triangle with shape of [N, ].
    """
    a = np.sqrt((v0[:, 0] - v1[:, 0])**2 + (v0[:, 1] - v1[:, 1])**2 + (
        v0[:, 2] - v1[:, 2])**2 + 1e-10)
    b = np.sqrt((v1[:, 0] - v2[:, 0])**2 + (v1[:, 1] - v2[:, 1])**2 + (
        v1[:, 2] - v2[:, 2])**2 + 1e-10)
    c = np.sqrt((v0[:, 0] - v2[:, 0])**2 + (v0[:, 1] - v2[:, 1])**2 + (
        v0[:, 2] - v2[:, 2])**2 + 1e-10)
    s = (a + b + c) / 2
    area = np.sqrt(s * (s - a) * (s - b) * (s - c) + 1e-10)
    return area


def sample_triangle(v0: np.ndarray, v1: np.ndarray, v2: np.ndarray,
                    n: int) -> np.ndarray:
    """
    Uniformly sample n points in an 3D triangle defined by 3 vertices v0, v1, v2
    https://math.stackexchange.com/questions/18686/uniform-random-point-in-triangle

    Args:
        v0 (np.ndarray): Coordinates of the first vertex of an triangle with shape of [3, ].
        v1 (np.ndarray): Coordinates of the second vertex of an triangle with shape of [3, ].
        v2 (np.ndarray): Coordinates of the third vertex of an triangle with shape of [3, ].
        n (int): Number of points to be sampled.

    Returns:
        np.ndarray: Coordinates of sampled n points.
    """
    r1 = np.random.uniform(0, 1, size=n)
    r2 = np.random.uniform(0, 1, size=n)
    s1 = np.sqrt(r1)
    x = v0[0] * (1.0 - s1) + v1[0] * (1.0 - r2) * s1 + v2[0] * r2 * s1
    y = v0[1] * (1.0 - s1) + v1[1] * (1.0 - r2) * s1 + v2[1] * r2 * s1
    z = v0[2] * (1.0 - s1) + v1[2] * (1.0 - r2) * s1 + v2[2] * r2 * s1
    return np.stack([x, y, z], axis=1)


class Mesh(Geometry):
    """A geometry represented by a point cloud, i.e., a set of points in space.

    Args:
        mesh(str, Mesh): Mesh file path, such as "/root/of/self.py_mesh.stl".
    """

    def __init__(self, mesh: Union[str, pymesh.Mesh]):
        if isinstance(mesh, str):
            self.py_mesh = pymesh.meshio.load_mesh(mesh)
        elif isinstance(mesh, pymesh.Mesh):
            self.py_mesh = mesh
        else:
            raise ValueError(f"type of mesh({type(mesh)} must be str or pymesh.Mesh")

        self.np_mesh = np_mesh.Mesh(np.zeros(self.py_mesh.faces.shape[0], dtype=np_mesh.Mesh.dtype))
        self.np_mesh.vectors = self.py_mesh.vertices[self.py_mesh.faces]
        self.num_faces = self.py_mesh.num_faces
        self.num_points = self.py_mesh.num_vertices
        self.points = self.py_mesh.vertices
        self.sdf = pysdf.SDF(self.py_mesh.vertices, self.py_mesh.faces)
        self.face_bounary = (
            ((np.min(self.np_mesh.vectors[:, :, 0])),
             np.max(self.np_mesh.vectors[:, :, 0])),
            ((np.min(self.np_mesh.vectors[:, :, 1])),
             np.max(self.np_mesh.vectors[:, :, 1])),
            ((np.min(self.np_mesh.vectors[:, :, 2])),
             np.max(self.np_mesh.vectors[:, :, 2]))
        )
        self.boundary_points = None
        self.boundary_normals = None
        super().__init__(
            self.points.shape[-1],
            (np.amin(self.points, axis=0), np.amax(self.points, axis=0)),
            np.inf
        )

    def inside(self, x: np.ndarray) -> np.ndarray:
        """_summary_

        Args:
            x (np.ndarray): [N, D]

        Returns:
            np.ndarray(bool): [N, ]
        """
        return self.sdf.contains(x)

    def on_boundary(self, x: np.ndarray) -> np.ndarray:
        """_summary_

        Args:
            x (np.ndarray): [N, D]

        Returns:
            np.ndarray(bool): [N, ]
        """
        inner_mask = self.sdf.contains(x)
        return ~inner_mask

    def random_points(self, n, random="pseudo") -> np.ndarray:
        cur_n = 0
        all_points = []
        while cur_n < n:
            random_points = [
                np.random.uniform(
                    e[0], e[1], size=n) for e in self.face_bounary
            ]
            random_points = np.stack(random_points, axis=1)
            inner_mask = self.sdf.contains(random_points)
            valid_random_points = random_points[inner_mask]

            all_points.append(valid_random_points)
            cur_n += len(valid_random_points)

        all_points = np.concatenate(all_points, axis=0)
        if cur_n > n:
            all_points = all_points[:n]
        return all_points

    def random_boundary_points(self, n, random="pseudo"):
        triangle_areas = area_of_triangles(
            self.np_mesh.v0,
            self.np_mesh.v1,
            self.np_mesh.v2
        )
        triangle_probabilities = triangle_areas / np.linalg.norm(triangle_areas, ord=1)
        triangle_index = np.arange(triangle_probabilities.shape[0])
        points_per_triangle = np.random.choice(triangle_index, n, p=triangle_probabilities)
        points_per_triangle, _ = np.histogram(
            points_per_triangle,
            np.arange(triangle_probabilities.shape[0] + 1) - 0.5
        )

        all_points = []
        for index, nr_p in enumerate(points_per_triangle):
            if nr_p == 0:
                continue
            sampled_points = sample_triangle(self.np_mesh.v0[index],
                                             self.np_mesh.v1[index],
                                             self.np_mesh.v2[index], nr_p)
            all_points.append(sampled_points)

        return np.concatenate(all_points, axis=0)

    def union(self, rhs: Mesh):
        csg = pymesh.CSGTree({
            "union": [
                {"mesh": self.py_mesh}, {"mesh": rhs.py_mesh}
            ]
        })
        return Mesh(csg.mesh)

    def __or__(self, rhs):
        return self.union(rhs)

    def difference(self, rhs):
        csg = pymesh.CSGTree({
            "difference": [
                {"mesh": self.py_mesh}, {"mesh": rhs.py_mesh}
            ]
        })
        return Mesh(csg.mesh)

    def __sub__(self, rhs):
        return self.difference(rhs)

    def intersection(self, rhs):
        csg = pymesh.CSGTree({
            "intersection": [
                {"mesh": self.py_mesh}, {"mesh": rhs.py_mesh}
            ]
        })
        return Mesh(csg.mesh)

    def __and__(self, rhs):
        return self.intersection(rhs)
