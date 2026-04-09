"""桌面上標的物（Cube/Sphere）建立與質心／模擬時間等 USD 工具。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from set_scene import SceneSetup

# 桌面上標的物尺寸（公尺）與相對桌面中心的 XY 偏移
LCUBE = 0.20
WCUBE = 0.16
HCUBE = 0.12
RSPHERE = 0.08
CUBE_OFFSET_XY = (0.35, 0.25)
SPHERE_OFFSET_XY = (-0.40, 0.30)

CUBE_PRIM_PATH = "/World/Cube"
SPHERE_PRIM_PATH = "/World/Sphere"


def get_isaac_sim_time_and_tc() -> tuple[float, Any]:
    """回傳 (模擬時間秒數, 對應 USD TimeCode)。"""
    from pxr import Usd

    try:
        import omni.timeline

        t = float(omni.timeline.get_timeline_interface().get_current_time())
        return t, Usd.TimeCode(t)
    except Exception:
        return 0.0, Usd.TimeCode.Default()


def get_physics_stage_time_code():
    return get_isaac_sim_time_and_tc()[1]


def get_prim_uniform_centroid_world(stage, prim_path: str, time_code=None) -> tuple[float, float, float]:
    """均勻密度下幾何質心：對稱 Gprim 之局部原點轉世界座標。"""
    from pxr import Gf, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        raise RuntimeError(f"找不到 prim: {prim_path}")
    tc = time_code if time_code is not None else get_physics_stage_time_code()
    xf = UsdGeom.Xformable(prim)
    m = xf.ComputeLocalToWorldTransform(tc)
    p = m.Transform(Gf.Vec3d(0.0, 0.0, 0.0))
    return (float(p[0]), float(p[1]), float(p[2]))


def get_prim_world_center(stage, prim_path: str) -> tuple[float, float, float]:
    """向後相容別名，行為與 get_prim_uniform_centroid_world 相同。"""
    return get_prim_uniform_centroid_world(stage, prim_path, None)


def spawn_red_table_objects(world, scene_setup: SceneSetup) -> list[dict]:
    """在 /World/Cube（紅）、/World/Sphere（綠）建立標的物，並回傳 Real_Object_list 初始資料。"""
    from pxr import Gf, UsdGeom

    stage = world.stage
    t_center = scene_setup.table_center
    top_z = scene_setup.table_top_z

    cx = float(t_center[0] + CUBE_OFFSET_XY[0])
    cy = float(t_center[1] + CUBE_OFFSET_XY[1])
    cz_cube = float(top_z + HCUBE * 0.5)

    sx = float(t_center[0] + SPHERE_OFFSET_XY[0])
    sy = float(t_center[1] + SPHERE_OFFSET_XY[1])
    cz_sphere = float(top_z + RSPHERE)

    cube = UsdGeom.Cube.Define(stage, CUBE_PRIM_PATH)
    cube.GetSizeAttr().Set(2.0)
    cube_prim = cube.GetPrim()
    xf_c = UsdGeom.Xformable(cube_prim)
    xf_c.ClearXformOpOrder()
    xf_c.AddTranslateOp().Set(Gf.Vec3d(cx, cy, cz_cube))
    xf_c.AddScaleOp().Set(Gf.Vec3d(LCUBE * 0.5, WCUBE * 0.5, HCUBE * 0.5))
    g_c = UsdGeom.Gprim(cube_prim)
    g_c.CreateDisplayColorAttr([(1.0, 0.0, 0.0)])

    sph = UsdGeom.Sphere.Define(stage, SPHERE_PRIM_PATH)
    sph.GetRadiusAttr().Set(float(RSPHERE))
    sph_prim = sph.GetPrim()
    xf_s = UsdGeom.Xformable(sph_prim)
    xf_s.ClearXformOpOrder()
    xf_s.AddTranslateOp().Set(Gf.Vec3d(sx, sy, cz_sphere))
    g_s = UsdGeom.Gprim(sph_prim)
    g_s.CreateDisplayColorAttr([(0.0, 1.0, 0.0)])

    for _ in range(8):
        world.step(render=False)

    _, time_code = get_isaac_sim_time_and_tc()
    center_cube = get_prim_uniform_centroid_world(stage, CUBE_PRIM_PATH, time_code)
    center_sphere = get_prim_uniform_centroid_world(stage, SPHERE_PRIM_PATH, time_code)

    return [
        {
            "datatype": "Cube",
            "name": "RedCube",
            "prim": CUBE_PRIM_PATH,
            "color": "red",
            "Lcube": float(LCUBE),
            "Wcube": float(WCUBE),
            "Hcube": float(HCUBE),
            "center": list(center_cube),
        },
        {
            "datatype": "Sphere",
            "name": "GreenSphere",
            "prim": SPHERE_PRIM_PATH,
            "color": "green",
            "Radius": float(RSPHERE),
            "center": list(center_sphere),
        },
    ]