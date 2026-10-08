"""A deliberately bounded ArUco fixture detector; not a general box detector."""
import cv2
import numpy as np
from .domain import Observation

DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
DETECTOR = cv2.aruco.ArucoDetector(DICTIONARY)
WIDTH, HEIGHT = 640, 400


def analyze(rgb: np.ndarray, packet: dict, task: dict) -> Observation:
    corners, ids, _ = DETECTOR.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    found = [] if ids is None else ids.flatten().tolist()
    relation, reason, bbox = 'unknown', '目标不可见或标记无法识别', None
    if task['target_marker'] in found:
        box = corners[found.index(task['target_marker'])][0]
        h, w = rgb.shape[:2]
        x1, y1 = box.min(axis=0) / [w, h]
        x2, y2 = box.max(axis=0) / [w, h]
        bbox = [float(x1), float(y1), float(x2), float(y2)]
        x, y = box.mean(axis=0) / [w, h]
        rx1, ry1, rx2, ry2 = task['roi'][packet['device_id']]
        margin = .025
        if min(abs(x-rx1), abs(x-rx2)) < margin and ry1-margin <= y <= ry2+margin:
            reason = '目标靠近区域边界'
        elif min(abs(y-ry1), abs(y-ry2)) < margin and rx1-margin <= x <= rx2+margin:
            reason = '目标靠近区域边界'
        else:
            relation = 'inside' if rx1 < x < rx2 and ry1 < y < ry2 else 'outside'
            reason = '依据目标标记中心与该视角区域判断'
    elif found:
        reason = '检测到其他标记，未找到绑定目标'
    return Observation(**packet, relation=relation, reason=reason, bbox=bbox, marker_ids=found)


def stamp(rgb: np.ndarray, captured_at: float, generation: int):
    """Synthetic capture timestamp survives RTSP encoding; it isn't inferred from receive time."""
    value = (int(captured_at * 1000) << 16) | (generation & 0xffff)
    rgb[380:397, 18:406] = 255
    for bit in range(64):
        color = 240 if (value >> (63-bit)) & 1 else 8
        rgb[383:394, 20+bit*6:26+bit*6] = color


def read_stamp(rgb: np.ndarray) -> tuple[float, int]:
    value = 0
    for bit in range(64):
        value = (value << 1) | int(rgb[386:391, 22+bit*6:24+bit*6].mean() > 128)
    return (value >> 16) / 1000, value & 0xffff
