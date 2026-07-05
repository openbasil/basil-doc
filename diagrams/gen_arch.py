#!/usr/bin/env python3
"""Generate the Basil architecture excalidraw diagram (clean, deterministic)."""

import json, sys

elements = []
_seed = [1000]


def nxt():
    _seed[0] += 7
    return _seed[0]


def rect(id, x, y, w, h, stroke, bg, sw=2, round=True):
    elements.append(
        {
            "id": id,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": stroke,
            "backgroundColor": bg,
            "fillStyle": "solid",
            "strokeWidth": sw,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 3} if round else None,
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
        }
    )


def text(id, x, y, w, h, s, color, size=16, align="center"):
    lines = s.count("\n") + 1
    elements.append(
        {
            "id": id,
            "type": "text",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "text": s,
            "fontSize": size,
            "fontFamily": 2,
            "textAlign": align,
            "verticalAlign": "middle",
            "baseline": int(size * 0.9 * lines),
            "containerId": None,
            "originalText": s,
            "lineHeight": 1.25,
        }
    )


def arrow(id, x, y, dx, dy, label_off=None):
    elements.append(
        {
            "id": id,
            "type": "arrow",
            "x": x,
            "y": y,
            "width": abs(dx),
            "height": abs(dy),
            "angle": 0,
            "strokeColor": "#5b6670",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 2},
            "seed": nxt(),
            "version": 1,
            "versionNonce": nxt(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "points": [[0, 0], [dx, dy]],
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
        }
    )


GREEN = "#1f7a4d"
DGREEN = "#13603a"
INK = "#1c2420"
MUTE = "#44504a"
GREY = "#5b6670"

# --- Workload ---
rect("wl", 40, 214, 190, 116, MUTE, "#eef3ef")
text("wl_t", 55, 246, 160, 52, "Workload / app\nor basil CLI", INK, 17)

# --- Basil broker ---
rect("basil", 360, 86, 444, 348, GREEN, "#ffffff", sw=2)
text("basil_t", 380, 104, 404, 26, "Basil broker", DGREEN, 22)
# three gate steps
rect("s1", 386, 150, 392, 70, GREEN, "#eef7f1", sw=1)
text(
    "s1_t",
    398,
    162,
    368,
    46,
    "1 · Attest the caller\nkernel SO_PEERCRED  (uid · gid · pid)",
    INK,
    15,
)
rect("s2", 386, 232, 392, 70, GREEN, "#eef7f1", sw=1)
text("s2_t", 398, 244, 368, 46, "2 · Check policy\ndefault-deny allow-list", INK, 15)
rect("s3", 386, 314, 392, 70, GREEN, "#eef7f1", sw=1)
text(
    "s3_t",
    398,
    326,
    368,
    46,
    "3 · Broker the operation\nsign · encrypt · mint in place",
    INK,
    15,
)

# --- Backends: in-place transit (keys stay put) ---
rect("be", 944, 150, 236, 150, MUTE, "#eef3ef")
text(
    "be_t",
    944,
    166,
    236,
    118,
    "In-place transit backends\n\nOpenBao · Vault\nAWS KMS · GCP KMS\n\nkeys live here,\nand stay here",
    INK,
    14,
)

# --- Backends: store-only (materialize-to-use) ---
rect("be2", 944, 320, 236, 150, MUTE, "#eef3ef")
text(
    "be2_t",
    944,
    336,
    236,
    118,
    "Store-only backends\n\ndb-keystore · 1Password\n\nmaterialize-to-use:\nkey in memory for one op",
    INK,
    14,
)

# --- Audit ---
rect("audit", 470, 482, 224, 66, GREY, "#f1f3f5")
text("audit_t", 482, 496, 200, 40, "Audit log\nevery decision recorded", INK, 14)

# --- Arrows ---
arrow("a_wl", 232, 272, 126, 0)  # workload -> basil
arrow("a_be", 806, 225, 136, 0)  # basil -> in-place transit backend
arrow("a_be2", 806, 395, 136, 0)  # basil -> store-only backend
arrow("a_au", 582, 434, 0, 46)  # basil -> audit

# --- Arrow labels ---
text("l_sock", 232, 238, 128, 20, "local socket · gRPC", GREY, 13)
text("l_op", 806, 191, 138, 20, "operation, in place", GREY, 13)
text("l_mat", 806, 361, 138, 20, "materialize-to-use", GREY, 13)

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
    "files": {},
}
out = sys.argv[1] if len(sys.argv) > 1 else "architecture.excalidraw"
with open(out, "w") as f:
    json.dump(doc, f, indent=2)
print("wrote", out, "with", len(elements), "elements")
