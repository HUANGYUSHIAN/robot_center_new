# import os
# import random
# from isaacsim import SimulationApp

# # 1. 初始化 SimulationApp
# simulation_app = SimulationApp({"headless": False})

# # 這些 import 必須在 SimulationApp 初始化之後
# import omni.usd
# from omni.isaac.core.utils.nucleus import get_assets_root_path
# from omni.isaac.core.utils.stage import open_stage, save_stage
# from pxr import UsdGeom, Gf, UsdPhysics

# def spawn_random_procedural_objects(stage, count=5):
#     """
#     不使用外部 USD，直接在 stage 上定義幾何體並賦予隨機位置與物理。
#     """
#     # 定義五種基本形狀的工廠函式
#     shapes = [
#         ("Cube", UsdGeom.Cube.Define),
#         ("Sphere", UsdGeom.Sphere.Define),
#         ("Cylinder", UsdGeom.Cylinder.Define),
#         ("Cone", UsdGeom.Cone.Define),
#         ("Capsule", UsdGeom.Capsule.Define)
#     ]

#     for i in range(count):
#         shape_name, shape_func = random.choice(shapes)
#         prim_path = f"/World/RandomObject_{i}_{shape_name}"
        
#         # 1. 定義幾何體
#         geom = shape_func(stage, prim_path)
#         prim = stage.GetPrimAtPath(prim_path)

#         # 2. 設定隨機變換 (Transform)
#         # 假設 Warehouse 中心附近範圍: X[-5, 5], Y[-5, 5], Z[3, 6]
#         pos = Gf.Vec3d(
#             random.uniform(-5.0, 5.0),
#             random.uniform(-5.0, 5.0),
#             random.uniform(3.0, 6.0)
#         )
        
#         # 設定隨機大小 (0.2m ~ 0.5m)
#         scale = random.uniform(0.2, 0.5)
        
#         # 套用 Transform Ops
#         xformable = UsdGeom.Xformable(prim)
#         xformable.AddTranslateOp().Set(pos)
#         xformable.AddScaleOp().Set(Gf.Vec3f(scale, scale, scale))
        
#         # 如果是球體或圓柱，可以額外微調屬性
#         if shape_name == "Sphere":
#             geom.GetRadiusAttr().Set(1.0) # 實際大小會被 Scale 縮放
        
#         # 3. 賦予物理屬性
#         UsdPhysics.CollisionAPI.Apply(prim)
#         rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
#         rigid_body.CreateRigidBodyEnabledAttr(True)
        
#         print(f"[Spawned] {shape_name} at {pos}")

# def build_scene():
#     # 2. 取得當前工作目錄的絕對路徑並指定本地檔案名稱
#     current_dir = os.getcwd()
    
#     local_filename = "YS_Scene_v1.usd"
#     warehouse_path = os.path.join(current_dir, local_filename)
    
#     if not open_stage(warehouse_path):
#         print("Failed to open warehouse stage.")
#         return

#     # 等待同步
#     for _ in range(60):
#         simulation_app.update()

#     stage = omni.usd.get_context().get_stage()

#     # 3. 生成隨機幾何物件
#     spawn_random_procedural_objects(stage, count=8)

#     print("\n--- Scene Ready ---")
#     print("請點擊 GUI 的 'Play' 按鈕觀看物理掉落效果。")

# # 執行場景建構
# build_scene()

# # 4. 主循環：保持 GUI 運行
# while simulation_app.is_running():
#     simulation_app.update()


# simulation_app.close()

import os
import random
from isaacsim import SimulationApp

# 1. 初始化 SimulationApp
simulation_app = SimulationApp({"headless": False})

import omni.usd
from omni.isaac.core.utils.stage import open_stage, save_stage
from pxr import UsdGeom, Gf, UsdPhysics, Usd

def spawn_random_objects_on_table(stage, table_path="/World/Table", count=8):
    """
    偵測桌子邊界，並在桌面上方隨機生成幾何體。
    """
    table_prim = stage.GetPrimAtPath(table_path)
    if not table_prim.IsValid():
        print(f"Error: 找不到桌子路徑 {table_path}")
        return

    # 計算桌子的世界座標邊界 (Bounding Box)
    # ComputeWorldBound 會考慮到 Translate, Rotate, Scale
    imageable = UsdGeom.Imageable(table_prim)
    time = Usd.TimeCode.Default()
    bound = imageable.ComputeWorldBound(time, "default")
    range_box = bound.GetRange()
    
    min_pt = range_box.GetMin()
    max_pt = range_box.GetMax()

    # 取得桌面的高度 (Z 的最大值)
    table_top_z = max_pt[2]
    
    # 取得長寬範圍 (稍微縮減 10% 避免物件掉到桌緣外)
    margin = 0.1 
    x_min, x_max = min_pt[0] + margin, max_pt[0] - margin
    y_min, y_max = min_pt[1] + margin, max_pt[1] - margin

    shapes = [
        ("Cube", UsdGeom.Cube.Define),
        ("Sphere", UsdGeom.Sphere.Define),
        ("Cylinder", UsdGeom.Cylinder.Define),
        ("Cone", UsdGeom.Cone.Define)
    ]

    print(f"偵測到桌面範圍: X({x_min:.2f}, {x_max:.2f}), Y({y_min:.2f}, {y_max:.2f}), Z_Height: {table_top_z:.2f}")

    for i in range(count):
        shape_name, shape_func = random.choice(shapes)
        prim_path = f"/World/RandomObject_{i}_{shape_name}"
        
        geom = shape_func(stage, prim_path)
        prim = stage.GetPrimAtPath(prim_path)

        # 隨機位置：在桌面長寬內，高度設定在桌面垂直上方 0.5m ~ 1.5m 處墜落
        pos = Gf.Vec3d(
            random.uniform(x_min, x_max),
            random.uniform(y_min, y_max),
            table_top_z + random.uniform(0.5, 1.5)
        )
        
        # 配合你桌子的大小 (10m x 4.8m)，隨機物件縮放可以設大一點 (0.3m ~ 0.6m)
        scale_val = random.uniform(0.3, 0.6)
        
        xformable = UsdGeom.Xformable(prim)
        xformable.AddTranslateOp().Set(pos)
        xformable.AddScaleOp().Set(Gf.Vec3f(scale_val, scale_val, scale_val))
        
        # 物理屬性
        UsdPhysics.CollisionAPI.Apply(prim)
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
        rigid_body.CreateRigidBodyEnabledAttr(True)
        
        print(f"[Spawned] {shape_name} at {pos}")

def build_scene():
    current_dir = os.getcwd()
    # 載入你之前儲存的包含 Table 的場景
    local_filename = "YS_Scene_v1.usd"
    warehouse_path = os.path.join(current_dir, local_filename)
    
    if not os.path.exists(warehouse_path):
        print(f"找不到檔案: {warehouse_path}，請確認檔名正確。")
        return

    if not open_stage(warehouse_path):
        print("無法開啟場景。")
        return

    # 等待 USD 載入與邊界計算預熱
    for _ in range(100):
        simulation_app.update()

    stage = omni.usd.get_context().get_stage()

    # 執行隨機生成函數
    spawn_random_objects_on_table(stage, table_path="/World/Table", count=10)

    print("\n--- 準備完成 ---")
    print("請點擊 Play 鍵查看物件墜落至桌面的效果。")

# 執行建構
build_scene()

# 主循環
while simulation_app.is_running():
    simulation_app.update()


simulation_app.close()