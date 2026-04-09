from __future__ import annotations

import base64
import random

import cv2
import numpy as np

from set_objects import (
    CUBE_PRIM_PATH,
    SPHERE_PRIM_PATH,
    get_isaac_sim_time_and_tc,
    get_prim_uniform_centroid_world,
)
from set_scene import load_scene, spawn_robot_and_cameras

DIGITAL_FPS = 4
TOP_FPS = 4
FRAME_SIZE = (320, 320)
JPEG_QUALITY = 40
SIM_STEP_HZ = 60
RANDOM_MOVE_INTERVAL_STEPS = 24


class RobotControlRuntime:
    def __init__(self, scene_dir):
        from isaacsim import SimulationApp

        self._headless = True
        self._sim = SimulationApp({"headless": self._headless})
        scene_setup = load_scene(self._sim, scene_dir)

        from omni.isaac.core import World
        from omni.isaac.core.utils.types import ArticulationAction

        self._world = World(stage_units_in_meters=1.0)
        self._action_cls = ArticulationAction
        self._robot, self._cam_robot, self._cam_top, self._cam_side, self._real_object_list_init = (
            spawn_robot_and_cameras(self._world, scene_setup)
        )

        self.dof_names = list(self._robot.dof_names)
        self._tick = 0
        self._latest_digital = ""
        self._latest_top = ""
        self._latest_side = ""
        self._last_digital_tick = -10_000
        self._last_top_tick = -10_000
        self._last_side_tick = -10_000
        self._capture_digital_every = max(1, int(SIM_STEP_HZ / DIGITAL_FPS))
        self._capture_top_every = max(1, int(SIM_STEP_HZ / TOP_FPS))
        self._capture_side_every = max(1, int(SIM_STEP_HZ / TOP_FPS))

    def _encode_camera(self, camera) -> str:
        rgba_data = camera.get_rgba()
        if rgba_data is None or rgba_data.ndim != 3:
            return ""
        bgr = cv2.cvtColor(rgba_data[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2BGR)
        ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            return ""
        return base64.b64encode(encoded.tobytes()).decode("ascii")

    def step(self) -> None:
        if self._tick % RANDOM_MOVE_INTERVAL_STEPS == 0:
            target = np.random.uniform(-0.7, 0.7, size=self._robot.num_dof)
            self._robot.apply_action(self._action_cls(joint_positions=target))
        elif random.random() < 0.05:
            target = np.random.uniform(-0.2, 0.2, size=self._robot.num_dof)
            self._robot.apply_action(self._action_cls(joint_positions=target))

        self._world.step(render=True)
        self._tick += 1

        if self._tick - self._last_digital_tick >= self._capture_digital_every:
            self._sim.update()
            self._latest_digital = self._encode_camera(self._cam_robot)
            self._last_digital_tick = self._tick
        if self._tick - self._last_top_tick >= self._capture_top_every:
            self._sim.update()
            self._latest_top = self._encode_camera(self._cam_top)
            self._last_top_tick = self._tick
        if self._tick - self._last_side_tick >= self._capture_side_every:
            self._sim.update()
            self._latest_side = self._encode_camera(self._cam_side)
            self._last_side_tick = self._tick

    def get_joint_values(self) -> list[float]:
        return [float(v) for v in self._robot.get_joint_positions()]

    def get_digital_frame(self) -> str:
        return self._latest_digital

    def get_top_frame(self) -> str:
        return self._latest_top

    def get_side_frame(self) -> str:
        return self._latest_side

    @property
    def real_object_list_init(self) -> list[dict]:
        return self._real_object_list_init

    def get_real_object_pose_update(self) -> tuple[list[dict], float]:
        sim_t, tc = get_isaac_sim_time_and_tc()
        stage = self._world.stage
        objects = [
            {"prim": CUBE_PRIM_PATH, "center": list(get_prim_uniform_centroid_world(stage, CUBE_PRIM_PATH, tc))},
            {"prim": SPHERE_PRIM_PATH, "center": list(get_prim_uniform_centroid_world(stage, SPHERE_PRIM_PATH, tc))},
        ]
        return objects, sim_t

    def close(self) -> None:
        if self._sim is not None:
            self._sim.close()
            self._sim = None
