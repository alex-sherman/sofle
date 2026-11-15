"""
Generate 3D-printable Bottom Case (.step and .stl) for Sofle_v2_soldered (V1 Keyboard Build).

Hardware specifications matched:
- PCB: c:/Code/sofle-nuphy/Sofle_v2_soldered/PCB/SofleKeyboard.kicad_pcb
  - 1.60 mm reversible 2-layer FR4 PCB
  - 58x direct-soldered NuPhy Nano (KS-33 Low Profile 3.0) switches (5.0 mm center stem hole), plateless
  - 58x 1N4148W (SOD-123) SMD diodes on the bottom side (~1.25 mm tall)
  - Socketed nice!nano v2 / SuperMini nRF52840 MCU + 301230 LiPo battery + slide switch on top inner bay,
    with through-hole header pins soldered on the bottom side (x=92.15..107.85, y=42.74..70.68, plus
    clearance to y=76.0 mm for shifted socket pins).
  - 5x primary mounting holes TH3-TH7 (4.10 mm drill on PCB):
      TH3: (129.30, 59.60)
      TH4: (205.80, 66.21)
      TH5: (129.30, 97.51)
      TH6: (205.80, 104.51)
      TH7: (103.80, 120.81)
  - 2x inner-bay M2 mounting holes TH1-TH2 (2.20 mm drill on PCB):
      TH1: (95.130, 93.352)
      TH2: (105.130, 93.336)

Case Z-Stackup (Total Height = 6.60 mm):
- Z = 0.00 .. 1.00 mm (1.00 mm): Base Floor Lower (with 4.50 mm M2 nut/head counterbores at TH3-TH7 & 4.00 mm at TH1-TH2)
- Z = 1.00 .. 2.00 mm (1.00 mm): Base Floor Upper (solid floor with 2.20 mm M2 through-holes at TH1-TH7)
- Z = 2.00 .. 5.00 mm (3.00 mm): Component Cavity & Standoff Bosses
    - 3.00 mm deep recessed pocket clearing all bottom SMD diodes, switch stems/pins, and MCU solder joints
    - 1.20 mm perimeter support shelf under PCB edge (with extra relief pocket around U1 header pins)
    - 7x cylindrical standoff bosses at TH1-TH7 supporting the PCB at Z = 5.00 mm
- Z = 5.00 .. 6.40 mm (1.40 mm): Outer Retaining Lip (0.25 mm XY clearance around PCB) + 5x Stepped Locator Collars
    (3.95 mm OD, 2.20 mm ID) at TH3-TH7 that index inside the 4.10 mm PCB holes
- Z = 6.40 .. 6.60 mm (0.20 mm): Top of Outer Retaining Lip (flush with top of 1.60 mm PCB at Z = 6.60 mm)
"""

import math
import os
import subprocess
import tempfile
import pcbnew

PCB_PATH = r"c:\Code\sofle-nuphy\Sofle_v2_soldered\PCB\SofleKeyboard.kicad_pcb"
OUT_DIR = r"c:\Code\sofle-nuphy\Sofle_v2_soldered\Case"
KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# Mounting style: "heatset" (3.10 mm x 4.00 mm deep heat-set insert bores pressed from bottom,
#                        with 2.20 mm M2 clearance through Z=4.00..6.40 mm and 3.95 mm locator collars)
#             or "through" (2.20 mm M2 through-holes + bottom counterbores + TH3-TH7 collars)
MOUNT_MODE = "heatset"

# Case parameters (mm)
PCB_CLEARANCE_XY = 0.25      # Radial gap between PCB Edge.Cuts and inner face of case lip
OUTER_WALL_THICK = 2.20      # Thickness of outer retaining wall around the PCB
SHELF_UNDERLAP = 1.20        # How far the perimeter support shelf extends inward under the PCB edge
FLOOR_CBORE_HEIGHT = 1.00    # Z = 0.00 .. 1.00 mm (solid floor in heatset mode; counterbore in through mode)
FLOOR_BRIDGE_HEIGHT = 1.00   # Z = 1.00 .. 2.00 mm (bottom of 4.00 mm heatset bore / through-hole bridge)
CAVITY_DEPTH = 3.00          # Z = 2.00 .. 5.00 mm (3.00 mm clearance under PCB for diodes & switch pins)
COLLAR_HEIGHT = 1.40         # Z = 5.00 .. 6.40 mm (stepped 3.95 mm OD locator collar in through mode)
LIP_TOP_EXTRA = 0.20         # Z = 6.40 .. 6.60 mm (completes 1.60 mm lip height flush with top of PCB)

M2_CLEARANCE_DRILL = 2.20    # M2 screw clearance hole diameter (through mode)
M2_HEATSET_BORE = 3.10       # Pilot bore for M2x3mm / M2x4mm brass heat-set inserts (3.2-3.5 mm OD)
M2_CBORE_DIA_MAIN = 4.60     # Counterbore diameter on bottom for TH3-TH7 (through mode)
M2_CBORE_DIA_INNER = 4.00    # Counterbore diameter on bottom for TH1-TH2 (through mode)
TH_COLLAR_OD = 3.95          # Stepped locator boss OD for 4.10 mm PCB holes (through mode)

# Standoff pillar ODs in cavity (Z = 2.00 .. 5.00 mm), sized to clear nearby diode pads
BOSS_SPECS = {
    "TH3": (129.300, 59.600, 6.60, True,  M2_CBORE_DIA_MAIN),
    "TH4": (205.800, 66.210, 7.60, True,  M2_CBORE_DIA_MAIN),
    "TH5": (129.300, 97.510, 6.60, True,  M2_CBORE_DIA_MAIN),
    "TH6": (205.800, 104.510, 7.60, True, M2_CBORE_DIA_MAIN),
    "TH7": (103.800, 120.810, 7.60, True, M2_CBORE_DIA_MAIN),
}

# Center point for normalizing coordinates & mirroring Right half
REF_X = 153.0
REF_Y = 93.0


def circle_poly(cx_mm, cy_mm, radius_mm, segments=64):
    poly = pcbnew.SHAPE_POLY_SET()
    poly.NewOutline()
    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        x = cx_mm + radius_mm * math.cos(ang)
        y = cy_mm + radius_mm * math.sin(ang)
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    return poly


def rect_poly(x0_mm, y0_mm, x1_mm, y1_mm):
    poly = pcbnew.SHAPE_POLY_SET()
    poly.NewOutline()
    for x, y in [(x0_mm, y0_mm), (x1_mm, y0_mm), (x1_mm, y1_mm), (x0_mm, y1_mm)]:
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    return poly


def clone_poly(poly):
    return pcbnew.SHAPE_POLY_SET(poly)


def transform_pt(x_mm, y_mm, mirror_x=False):
    dx = x_mm - REF_X
    dy = y_mm - REF_Y
    if mirror_x:
        dx = -dx
    return REF_X + dx, REF_Y + dy


def add_polyset_to_board_edges(board, polyset, mirror_x=False):
    edge_layer = board.GetLayerID("Edge.Cuts")
    for i in range(polyset.OutlineCount()):
        outline = polyset.Outline(i)
        n = outline.PointCount()
        for j in range(n):
            p0 = outline.CPoint(j)
            p1 = outline.CPoint((j + 1) % n)
            x0, y0 = transform_pt(pcbnew.ToMM(p0.x), pcbnew.ToMM(p0.y), mirror_x)
            x1, y1 = transform_pt(pcbnew.ToMM(p1.x), pcbnew.ToMM(p1.y), mirror_x)
            seg = pcbnew.PCB_SHAPE(board)
            seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
            seg.SetLayer(edge_layer)
            seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
            seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            board.Add(seg)

        for h in range(polyset.HoleCount(i)):
            hole = polyset.Hole(i, h)
            nh = hole.PointCount()
            for j in range(nh):
                p0 = hole.CPoint(j)
                p1 = hole.CPoint((j + 1) % nh)
                x0, y0 = transform_pt(pcbnew.ToMM(p0.x), pcbnew.ToMM(p0.y), mirror_x)
                x1, y1 = transform_pt(pcbnew.ToMM(p1.x), pcbnew.ToMM(p1.y), mirror_x)
                seg = pcbnew.PCB_SHAPE(board)
                seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
                seg.SetLayer(edge_layer)
                seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
                seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                board.Add(seg)


def export_tier_step(polyset, thickness_mm, step_out_path, mirror_x=False):
    pcb_tmp = step_out_path.replace(".step", ".kicad_pcb")
    b = pcbnew.NewBoard(pcb_tmp)
    # KiCad subtracts 0.09 mm for default 2-layer copper+mask stackup when exporting board body
    b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(thickness_mm + 0.09))
    add_polyset_to_board_edges(b, polyset, mirror_x=mirror_x)
    pcbnew.SaveBoard(pcb_tmp, b)
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "step", "--board-only", "--grid-origin", "-f", "-o", step_out_path, pcb_tmp],
        check=True,
        capture_output=True,
        text=True,
    )


def build_case_tiers(pcb_poly):
    # Outer boundary of case: PCB + 0.25mm clearance + 2.20mm wall = +2.45mm
    outer_expand = PCB_CLEARANCE_XY + OUTER_WALL_THICK
    outer_poly = clone_poly(pcb_poly)
    outer_poly.Inflate(pcbnew.FromMM(outer_expand), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.02))

    # Lip inner boundary (where 1.6mm PCB sits): PCB + 0.25mm clearance
    lip_inner_poly = clone_poly(pcb_poly)
    lip_inner_poly.Inflate(pcbnew.FromMM(PCB_CLEARANCE_XY), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.02))

    # Cavity inner boundary (recessed 3.0mm pocket under PCB): PCB - 1.20mm shelf underlap
    cavity_cutout = clone_poly(pcb_poly)
    cavity_cutout.Inflate(pcbnew.FromMM(-SHELF_UNDERLAP), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.02))

    # Extra relief pocket for U1 Pro Micro / nice!nano through-hole pins (including shifted socket pins down to y=76mm)
    # U1 pads are at x=92.15..107.85, y=42.74..70.68 (and extra socket pin to y=75.5).
    # PCB edge is at x=89.73 and y=40.55. Let's give U1 cavity cutout out to x=90.45, y=41.25..76.0!
    u1_relief = rect_poly(90.45, 41.25, 109.50, 76.00)
    cavity_cutout.BooleanAdd(u1_relief)

    is_heatset = (MOUNT_MODE == "heatset")

    if is_heatset:
        # Heat-set inserts pressed from BOTTOM (Z = 0.00 .. 4.00 mm, 3.10 mm pilot bore)
        # Solid 1.00 mm bridge (Z = 4.00 .. 5.00 mm) + 3.95 mm stepped locator collars (Z = 5.00 .. 6.40 mm)
        # with 2.20 mm M2 screw clearance holes so screws drop in from the TOP of the PCB.
        tier_floor_insert = clone_poly(outer_poly)
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            tier_floor_insert.BooleanSubtract(circle_poly(bx, by, M2_HEATSET_BORE / 2.0))

        tier_cav_lower = clone_poly(outer_poly)
        tier_cav_lower.BooleanSubtract(cavity_cutout)
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            tier_cav_lower.BooleanAdd(circle_poly(bx, by, boss_od / 2.0))
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            tier_cav_lower.BooleanSubtract(circle_poly(bx, by, M2_HEATSET_BORE / 2.0))

        tier_cav_upper = clone_poly(outer_poly)
        tier_cav_upper.BooleanSubtract(cavity_cutout)
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            tier_cav_upper.BooleanAdd(circle_poly(bx, by, boss_od / 2.0))
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            tier_cav_upper.BooleanSubtract(circle_poly(bx, by, M2_CLEARANCE_DRILL / 2.0))

        tier_collar = clone_poly(outer_poly)
        tier_collar.BooleanSubtract(lip_inner_poly)
        for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
            if has_collar:
                tier_collar.BooleanAdd(circle_poly(bx, by, TH_COLLAR_OD / 2.0))
                tier_collar.BooleanSubtract(circle_poly(bx, by, M2_CLEARANCE_DRILL / 2.0))

        tier_lip = clone_poly(outer_poly)
        tier_lip.BooleanSubtract(lip_inner_poly)

        Z0 = -0.095  # Compensate for master board stackup offset so case bottom is at Z = 0.000 mm
        return [
            ("tier1_floor_ins", tier_floor_insert, 2.00,          Z0 + 0.00),
            ("tier2_cav_ins",   tier_cav_lower,    2.00,          Z0 + 2.00),
            ("tier3_cavity",    tier_cav_upper,    1.00,          Z0 + 4.00),
            ("tier4_collar",    tier_collar,       COLLAR_HEIGHT, Z0 + 5.00),
            ("tier5_lip",       tier_lip,          LIP_TOP_EXTRA, Z0 + 6.40),
        ]

    # Through-hole mode: bottom counterbores + 2.20 mm M2 clearance + 3.95 mm locator collars
    tier1 = clone_poly(outer_poly)
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        tier1.BooleanSubtract(circle_poly(bx, by, cbore_dia / 2.0))

    tier2 = clone_poly(outer_poly)
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        tier2.BooleanSubtract(circle_poly(bx, by, M2_CLEARANCE_DRILL / 2.0))

    tier3 = clone_poly(outer_poly)
    tier3.BooleanSubtract(cavity_cutout)
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        tier3.BooleanAdd(circle_poly(bx, by, boss_od / 2.0))
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        tier3.BooleanSubtract(circle_poly(bx, by, M2_CLEARANCE_DRILL / 2.0))

    tier4 = clone_poly(outer_poly)
    tier4.BooleanSubtract(lip_inner_poly)
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        if has_collar:
            tier4.BooleanAdd(circle_poly(bx, by, TH_COLLAR_OD / 2.0))
            tier4.BooleanSubtract(circle_poly(bx, by, M2_CLEARANCE_DRILL / 2.0))

    # Tier 5 (Z = 6.40 .. 6.60 mm): Top 0.20 mm of Outer Retaining Lip
    tier5 = clone_poly(outer_poly)
    tier5.BooleanSubtract(lip_inner_poly)

    Z0 = -0.095  # Compensate for master board stackup offset so case bottom is at Z = 0.000 mm
    return [
        ("tier1_cbore",  tier1, FLOOR_CBORE_HEIGHT,  Z0 + 0.00),
        ("tier2_floor",  tier2, FLOOR_BRIDGE_HEIGHT, Z0 + FLOOR_CBORE_HEIGHT),
        ("tier3_cavity", tier3, CAVITY_DEPTH,        Z0 + FLOOR_CBORE_HEIGHT + FLOOR_BRIDGE_HEIGHT),
        ("tier4_collar", tier4, COLLAR_HEIGHT,       Z0 + FLOOR_CBORE_HEIGHT + FLOOR_BRIDGE_HEIGHT + CAVITY_DEPTH),
        ("tier5_lip",    tier5, LIP_TOP_EXTRA,       Z0 + FLOOR_CBORE_HEIGHT + FLOOR_BRIDGE_HEIGHT + CAVITY_DEPTH + COLLAR_HEIGHT),
    ]


def assemble_and_export(tiers, side_name, mirror_x, tmp_dir):
    master_pcb_path = os.path.join(tmp_dir, f"master_{side_name}.kicad_pcb")
    master = pcbnew.NewBoard(master_pcb_path)
    master.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(0.1))

    for t_name, poly, thick_mm, z_off_mm in tiers:
        step_path = os.path.join(tmp_dir, f"{side_name}_{t_name}.step")
        export_tier_step(poly, thick_mm, step_path, mirror_x=mirror_x)

        fp = pcbnew.FOOTPRINT(master)
        fp.SetReference(t_name.upper())
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        m = pcbnew.FP_3DMODEL()
        m.m_Filename = step_path
        m.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, z_off_mm)
        m.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
        m.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
        m.m_Show = True
        fp.Add3DModel(m)
        master.Add(fp)

    pcbnew.SaveBoard(master_pcb_path, master)

    out_step = os.path.join(OUT_DIR, f"Sofle_v2_soldered_Bottom_Case_{side_name}.step")
    out_stl = os.path.join(OUT_DIR, f"Sofle_v2_soldered_Bottom_Case_{side_name}.stl")

    subprocess.run(
        [KICAD_CLI, "pcb", "export", "step", "--no-board-body", "--fuse-shapes", "--grid-origin", "-f", "-o", out_step, master_pcb_path],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "stl", "--no-board-body", "--fuse-shapes", "--grid-origin", "-f", "-o", out_stl, master_pcb_path],
        check=True,
        capture_output=True,
        text=True,
    )
    print(f"[{side_name}] Exported STEP: {out_step} ({os.path.getsize(out_step):,} bytes)")
    print(f"[{side_name}] Exported STL:  {out_stl} ({os.path.getsize(out_stl):,} bytes)")


def generate_m2_washers(tmp_dir):
    """Generate 10x M2 retaining washers (6.0mm OD, 2.2mm ID, 1.2mm thick) for TH3-TH7 top clamping."""
    washers_poly = pcbnew.SHAPE_POLY_SET()
    for i in range(10):
        col = i % 5
        row = i // 5
        cx = 100.0 + col * 8.0
        cy = 100.0 + row * 8.0
        w = circle_poly(cx, cy, 3.00)
        w.BooleanSubtract(circle_poly(cx, cy, 1.10))
        washers_poly.BooleanAdd(w)

    pcb_tmp = os.path.join(tmp_dir, "washers.kicad_pcb")
    b = pcbnew.NewBoard(pcb_tmp)
    b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.20 + 0.09))
    add_polyset_to_board_edges(b, washers_poly, mirror_x=False)
    pcbnew.SaveBoard(pcb_tmp, b)

    out_step = os.path.join(OUT_DIR, "Sofle_v2_soldered_M2_Washers_x10.step")
    out_stl = os.path.join(OUT_DIR, "Sofle_v2_soldered_M2_Washers_x10.stl")
    subprocess.run([KICAD_CLI, "pcb", "export", "step", "--board-only", "--grid-origin", "-f", "-o", out_step, pcb_tmp], check=True, capture_output=True)
    subprocess.run([KICAD_CLI, "pcb", "export", "stl", "--board-only", "--grid-origin", "-f", "-o", out_stl, pcb_tmp], check=True, capture_output=True)
    print(f"[Washers] Exported STEP & STL: {out_stl} ({os.path.getsize(out_stl):,} bytes)")


def render_blueprint(board, pcb_poly, tiers):
    from PIL import Image, ImageDraw

    W, H = 1800, 1350
    img = Image.new("RGB", (W, H), (18, 22, 28))
    draw = ImageDraw.Draw(img)

    # Coordinate transform: X in [75, 232] -> px, Y in [30, 156] -> py
    scale = 9.5
    ox, oy = -620, -220

    def to_px(x_mm, y_mm):
        return (int(round(x_mm * scale + ox)), int(round(y_mm * scale + oy)))

    def draw_polyset(polyset, fill_outline, fill_hole, outline_color, width=2):
        for i in range(polyset.OutlineCount()):
            ol = polyset.Outline(i)
            pts = [to_px(pcbnew.ToMM(ol.CPoint(j).x), pcbnew.ToMM(ol.CPoint(j).y)) for j in range(ol.PointCount())]
            if len(pts) >= 3:
                if fill_outline:
                    draw.polygon(pts, fill=fill_outline)
                draw.line(pts + [pts[0]], fill=outline_color, width=width)
            for h in range(polyset.HoleCount(i)):
                hl = polyset.Hole(i, h)
                hpts = [to_px(pcbnew.ToMM(hl.CPoint(j).x), pcbnew.ToMM(hl.CPoint(j).y)) for j in range(hl.PointCount())]
                if len(hpts) >= 3:
                    if fill_hole:
                        draw.polygon(hpts, fill=fill_hole)
                    draw.line(hpts + [hpts[0]], fill=outline_color, width=width)

    tier_dict = {name: poly for name, poly, _, _ in tiers}

    # 1. Draw Outer Retaining Lip (Z = 5.0..6.6mm) in bright cyan
    t5 = tier_dict["tier5_lip"]
    draw_polyset(t5, (90, 175, 220), (55, 110, 145), (170, 235, 255), width=2)

    # 2. Draw Recessed Component Cavity cutout (Z = 2.0mm floor) inside the shelf
    t3 = tier_dict["tier3_cavity"]
    main_idx = max(range(t3.OutlineCount()), key=lambda idx: t3.Outline(idx).PointCount())
    for h in range(t3.HoleCount(main_idx)):
        hl = t3.Hole(main_idx, h)
        hpts = [to_px(pcbnew.ToMM(hl.CPoint(j).x), pcbnew.ToMM(hl.CPoint(j).y)) for j in range(hl.PointCount())]
        if len(hpts) >= 3:
            draw.polygon(hpts, fill=(28, 34, 44))
            draw.line(hpts + [hpts[0]], fill=(110, 170, 210), width=2)

    # 3. Draw 7x Standoff Pillars (Z = 5.0mm) and 5x Stepped Locator Collars (Z = 6.4mm) + M2 holes
    for ref, (bx, by, boss_od, has_collar, cbore_dia) in BOSS_SPECS.items():
        r_boss = boss_od / 2.0
        draw.ellipse([to_px(bx - r_boss, by - r_boss), to_px(bx + r_boss, by + r_boss)],
                     fill=(65, 125, 160), outline=(140, 210, 245), width=2)
        if has_collar:
            r_col = TH_COLLAR_OD / 2.0
            draw.ellipse([to_px(bx - r_col, by - r_col), to_px(bx + r_col, by + r_col)],
                         fill=(105, 195, 240), outline=(200, 245, 255), width=2)
        r_m2 = M2_CLEARANCE_DRILL / 2.0
        draw.ellipse([to_px(bx - r_m2, by - r_m2), to_px(bx + r_m2, by + r_m2)],
                     fill=(18, 22, 28), outline=(255, 255, 255), width=2)
        lx, ly = to_px(bx + r_boss + 0.8, by - 1.2)
        draw.text((lx, ly), ref, fill=(255, 255, 255))

    # 4. Draw PCB Edge.Cuts outline in bright green
    draw_polyset(pcb_poly, None, None, (80, 240, 130), width=2)

    # 5. Overlay bottom-side PCB components (Switches, Diodes, U1 header pads) to verify clearance
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        layer = board.GetLayerName(fp.GetLayer())
        if ref in ("J1", "J2", "J3", "RSW1", "SW25", "D25") or ref.startswith("TH") or ref.startswith("JP") or ref.startswith("G"):
            continue
        if ref.startswith("SW") and layer == "F.Cu":
            for pad in fp.Pads():
                px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                r = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2.0
                draw.ellipse([to_px(px - r, py - r), to_px(px + r, py + r)], fill=(210, 160, 60), outline=(255, 210, 100))
        elif ref.startswith("D") and layer == "F.Cu":
            for pad in fp.Pads():
                px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                r = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2.0
                draw.ellipse([to_px(px - r, py - r), to_px(px + r, py + r)], fill=(220, 80, 80), outline=(255, 130, 130))
        elif ref == "U1":
            for pad in fp.Pads():
                px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                r = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2.0
                draw.ellipse([to_px(px - r, py - r), to_px(px + r, py + r)], fill=(190, 90, 230), outline=(230, 160, 255))

    out_png = os.path.join(OUT_DIR, "Sofle_v2_soldered_Bottom_Case_Blueprint.png")
    img.save(out_png)
    print(f"[Blueprint] Saved clearance verification blueprint: {out_png}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    board = pcbnew.LoadBoard(PCB_PATH)
    pcb_poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(pcb_poly, False)

    tiers = build_case_tiers(pcb_poly)
    render_blueprint(board, pcb_poly, tiers)

    with tempfile.TemporaryDirectory() as tmp_dir:
        assemble_and_export(tiers, "Left", mirror_x=False, tmp_dir=tmp_dir)
        assemble_and_export(tiers, "Right", mirror_x=True, tmp_dir=tmp_dir)
        generate_m2_washers(tmp_dir)


if __name__ == "__main__":
    main()
