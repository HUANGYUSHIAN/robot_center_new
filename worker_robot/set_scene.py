from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Robot 初始位置設定：
# - 設成 None：使用桌面正中心（default）
# - 設成 (x, y, z)：使用自訂世界座標
ROBOT_INITIAL_POSITION = [1.3, -0.4, 0.5]
PRINT_POSE_INTERVAL_SEC = 20.0

# Camera 位置可調設定：
# - Cam_Robot 為相對機器人座標（因為掛在 /World/A1 底下）
CAM_ROBOT_LOCAL_POSITION = (1.3, -0.4, 3.0)
CAM_ROBOT_EULER_DEG = (0.0, 90.0, 0.0)
# - Cam_Top 若設 None，則使用桌面中心自動計算；否則用自訂世界座標
CAM_TOP_WORLD_POSITION = [0.0, 0.0, 8.4]
CAM_TOP_EULER_DEG = (0.0, 90.0, 0.0)
CAM_SIDE_WORLD_POSITION = (10.0, 0.0, 0.8)
CAM_SIDE_EULER_DEG = (0.0, 0.0, 180.0)

SCENE_FILE = "YS_Scene_v1.usd"
TABLE_PRIM_PATH = "/World/Table"
ROBOT_PRIM_PATH = "/World/A1"
CAM_ROBOT_PRIM_PATH = f"{ROBOT_PRIM_PATH}/Cam_Robot"
CAM_TOP_PRIM_PATH = "/World/Cam_Top"
CAM_SIDE_PRIM_PATH = "/World/Cam_Side"


@dataclass
class SceneSetup:
    robot_position: np.ndarray
    table_center: np.ndarray
    table_top_z: float
    table_center_z: float


def _compute_world_bbox(stage, prim_path: str):
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        raise RuntimeError(f"找不到 prim: {prim_path}")
    bound = UsdGeom.Imageable(prim).ComputeWorldBound(Usd.TimeCode.Default(), "default")
    return bound.GetRange()


def _choose_robot_position(table_range, world_range) -> np.ndarray:
    table_min = np.array(table_range.GetMin(), dtype=np.float32)
    table_max = np.array(table_range.GetMax(), dtype=np.float32)
    world_min = np.array(world_range.GetMin(), dtype=np.float32)
    world_max = np.array(world_range.GetMax(), dtype=np.float32)

    if ROBOT_INITIAL_POSITION is not None:
        return np.array([float(v) for v in ROBOT_INITIAL_POSITION], dtype=np.float32)

    # default: 桌面正中心（略高於桌面避免初始穿模）
    table_center = (table_min + table_max) * 0.5
    candidate = np.array(
        [float(table_center[0]), float(table_center[1]), float(table_max[2] + DEFAULT_ROBOT_Z_OFFSET)],
        dtype=np.float32,
    )

    safe_min = world_min + np.array([0.5, 0.5, 0.0], dtype=np.float32)
    safe_max = world_max - np.array([0.5, 0.5, 0.0], dtype=np.float32)
    if (candidate[:2] >= safe_min[:2]).all() and (candidate[:2] <= safe_max[:2]).all():
        return candidate
    return np.array([0.0, 0.0, float(table_max[2] + DEFAULT_ROBOT_Z_OFFSET)], dtype=np.float32)


def load_scene(sim_app, scene_dir: Path) -> SceneSetup:
    import omni.usd
    from omni.isaac.core.utils.stage import open_stage

    stage_path = str((scene_dir / SCENE_FILE).resolve())
    if not open_stage(stage_path):
        raise RuntimeError(f"無法開啟場景: {stage_path}")

    for _ in range(120):
        sim_app.update()

    stage = omni.usd.get_context().get_stage()
    table_range = _compute_world_bbox(stage, TABLE_PRIM_PATH)
    world_range = _compute_world_bbox(stage, "/World")

    table_min = np.array(table_range.GetMin(), dtype=np.float32)
    table_max = np.array(table_range.GetMax(), dtype=np.float32)
    table_center = (table_min + table_max) * 0.5
    robot_pos = _choose_robot_position(table_range, world_range)
    return SceneSetup(
        robot_position=robot_pos,
        table_center=table_center,
        table_top_z=float(table_max[2]),
        table_center_z=float(table_center[2]),
    )


def spawn_robot_and_cameras(world, scene_setup: SceneSetup):
    import omni.isaac.core.utils.numpy.rotations as rot_utils
    from omni.isaac.core.robots import Robot
    from omni.isaac.core.utils.nucleus import get_assets_root_path
    from omni.isaac.core.utils.prims import add_reference_to_stage
    from omni.isaac.sensor import Camera
    from pxr import Gf, UsdGeom

    assets_root = get_assets_root_path()
    robot_asset_path = assets_root + "/Isaac/Robots/Unitree/A1/a1.usd"
    add_reference_to_stage(usd_path=robot_asset_path, prim_path=ROBOT_PRIM_PATH)

    for _ in range(80):
        world.step(render=False)

    robot_prim = world.stage.GetPrimAtPath(ROBOT_PRIM_PATH)
    xform = UsdGeom.Xformable(robot_prim)
    xform_ops = xform.GetOrderedXformOps()
    robot_pos = [float(v) for v in scene_setup.robot_position]
    if xform_ops:
        xform_ops[0].Set(Gf.Vec3d(*robot_pos))
    else:
        xform.AddTranslateOp().Set(Gf.Vec3d(*robot_pos))

    robot = world.scene.add(Robot(prim_path=ROBOT_PRIM_PATH, name="my_a1"))
    world.reset()

    cam_robot = Camera(
        prim_path=CAM_ROBOT_PRIM_PATH,
        position=np.array([float(v) for v in CAM_ROBOT_LOCAL_POSITION], dtype=np.float32),
        resolution=(320, 320),
        orientation=rot_utils.euler_angles_to_quats(np.array([float(v) for v in CAM_ROBOT_EULER_DEG], dtype=np.float32), degrees=True),
    )

    cam_top = Camera(
        prim_path=CAM_TOP_PRIM_PATH,
        position = np.array([float(v) for v in CAM_TOP_WORLD_POSITION], dtype=np.float32),
        resolution=(320, 320),
        orientation=rot_utils.euler_angles_to_quats(np.array([float(v) for v in CAM_TOP_EULER_DEG], dtype=np.float32), degrees=True),
    )
    cam_side = Camera(
        prim_path=CAM_SIDE_PRIM_PATH,
        position=np.array([float(v) for v in CAM_SIDE_WORLD_POSITION], dtype=np.float32),
        resolution=(320, 320),
        orientation=rot_utils.euler_angles_to_quats(np.array([float(v) for v in CAM_SIDE_EULER_DEG], dtype=np.float32), degrees=True),
    )
    cam_robot.initialize()
    cam_top.initialize()
    cam_side.initialize()
    return robot, cam_robot, cam_top, cam_side


class ExternalCameraViewer:
    """用 matplotlib 外部視窗顯示 Cam_Robot / Cam_Top / Cam_Side。"""

    def __init__(self) -> None:
        self.available = False
        self._plt = None
        self._fig = None
        self._ax_robot = None
        self._ax_top = None
        self._ax_side = None
        self._img_robot = None
        self._img_top = None
        self._img_side = None
        try:
            import matplotlib.pyplot as plt

            self._plt = plt
            self._plt.ion()
            self._fig, (self._ax_robot, self._ax_top, self._ax_side) = self._plt.subplots(1, 3, figsize=(15, 5))
            self._ax_robot.set_title("Cam_Robot View")
            self._ax_top.set_title("Cam_Top View")
            self._ax_side.set_title("Cam_Side View")
            self._ax_robot.axis("off")
            self._ax_top.axis("off")
            self._ax_side.axis("off")
            self.available = True
        except Exception as exc:
            print(f"[set_scene] 無法建立 matplotlib 視窗，略過外部 camera 顯示: {exc}")

    def update(self, cam_robot, cam_top, cam_side) -> None:
        if not self.available:
            return
        rgba_robot = cam_robot.get_rgba()
        rgba_top = cam_top.get_rgba()
        rgba_side = cam_side.get_rgba()
        if rgba_robot is None or rgba_top is None or rgba_side is None:
            return
        if getattr(rgba_robot, "ndim", 0) != 3 or getattr(rgba_top, "ndim", 0) != 3 or getattr(rgba_side, "ndim", 0) != 3:
            return

        rgb_robot = rgba_robot[:, :, :3].astype(np.uint8)
        rgb_top = rgba_top[:, :, :3].astype(np.uint8)
        rgb_side = rgba_side[:, :, :3].astype(np.uint8)

        if self._img_robot is None:
            self._img_robot = self._ax_robot.imshow(rgb_robot)
            self._img_top = self._ax_top.imshow(rgb_top)
            self._img_side = self._ax_side.imshow(rgb_side)
        else:
            self._img_robot.set_data(rgb_robot)
            self._img_top.set_data(rgb_top)
            self._img_side.set_data(rgb_side)

        self._fig.canvas.draw_idle()
        self._fig.canvas.flush_events()
        self._plt.pause(0.001)

    def close(self) -> None:
        if self.available and self._plt is not None and self._fig is not None:
            self._plt.close(self._fig)


def preview_scene(scene_dir: Path, headless: bool) -> None:
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": headless})
    viewer = ExternalCameraViewer() if not headless else None
    try:
        scene_setup = load_scene(simulation_app, scene_dir)
        from omni.isaac.core import World

        world = World(stage_units_in_meters=1.0)
        robot, cam_robot, cam_top, cam_side = spawn_robot_and_cameras(world, scene_setup)
        for _ in range(30):
            simulation_app.update()
        print(
            "[set_scene] ready:"
            f" robot={scene_setup.robot_position.tolist()}"
            f" table_center={scene_setup.table_center.tolist()}"
            f" table_top_z={scene_setup.table_top_z:.3f}"
        )
        last_print_ts = 0.0
        while simulation_app.is_running():
            simulation_app.update()
            if viewer is not None:
                viewer.update(cam_robot, cam_top, cam_side)
            now_ts = time.monotonic()
            if now_ts - last_print_ts >= PRINT_POSE_INTERVAL_SEC:
                robot_pos, _ = robot.get_world_pose()
                cam_robot_pos, _ = cam_robot.get_world_pose()
                cam_top_pos, _ = cam_top.get_world_pose()
                cam_side_pos, _ = cam_side.get_world_pose()
                print(
                    "[set_scene][pose]"
                    f" RobotCenter=({robot_pos[0]:.3f}, {robot_pos[1]:.3f}, {robot_pos[2]:.3f})"
                    f" Cam_Robot=({cam_robot_pos[0]:.3f}, {cam_robot_pos[1]:.3f}, {cam_robot_pos[2]:.3f})"
                    f" Cam_Top=({cam_top_pos[0]:.3f}, {cam_top_pos[1]:.3f}, {cam_top_pos[2]:.3f})"
                    f" Cam_Side=({cam_side_pos[0]:.3f}, {cam_side_pos[1]:.3f}, {cam_side_pos[2]:.3f})"
                )
                last_print_ts = now_ts
    finally:
        if viewer is not None:
            viewer.close()
        simulation_app.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TMUI set_scene standalone preview")
    parser.add_argument("--headless", action="store_true", help="run without GUI")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    preview_scene(scene_dir=Path(__file__).resolve().parent, headless=args.headless)
