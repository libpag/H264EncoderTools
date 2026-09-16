#!/usr/bin/env python3
"""H264EncoderTools 回归测试套件：覆盖协议正确性、帧完整性、安全边界和并发隔离。

测试用例（每个独立使用唯一工作目录）：
  1. test_basic_5frames       — 基础 5 帧编码，验证 header + 逐帧输出
  2. test_rapid_100frames     — 100 帧无延迟投递后立即结束，验证输出帧数完整
  3. test_truncated_yuv       — 截断 YUV 文件（小于 FrameSize），验证工具不越界
  4. test_empty_yuv           — 空 YUV 文件，验证工具报错而非崩溃
  5. test_wrong_framesize     — FrameSize 大于实际文件长度，验证有界读取
  6. test_concurrent          — 两个独立实例并发编码，互不干扰
  7. test_immediate_end       — 无帧直接 InEnd，验证工具不挂起且正常退出
  8. test_early_exit          — 投递若干帧后发送 EarlyExit=1，验证快速退出
  9. test_missing_param       — 无 EncoderParam.txt，验证工具报错退出
 10. test_determinism         — 开启 Deterministic 后重复编码 5 次，验证输出码流字节完全一致

注意：工作目录使用唯一路径（基于 pid + test name），不自动删除，便于调试。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "build", "H264EncoderTools")

# 默认编码参数
DEFAULT_W, DEFAULT_H = 32, 32
DEFAULT_FPS = 25.0
DEFAULT_QUALITY = 80
DEFAULT_MAX_KFI = 60


def make_work_dir(test_name):
    """创建唯一工作目录"""
    base = os.path.join(HERE, f"test_work_{os.getpid()}_{test_name}")
    os.makedirs(base, exist_ok=True)
    return base


def write_file(path, data, binary=False):
    mode = "wb" if binary else "w"
    tmp = path + "_temp"
    with open(tmp, mode) as f:
        f.write(data)
    os.rename(tmp, path)


def write_param(work_dir, w=DEFAULT_W, h=DEFAULT_H, fps=DEFAULT_FPS,
                has_alpha=0, quality=DEFAULT_QUALITY, max_kfi=DEFAULT_MAX_KFI):
    content = json.dumps({
        "Width": w, "Height": h, "FrameRate": fps,
        "HasAlpha": has_alpha, "MaxKeyFrameInterval": max_kfi, "Quality": quality
    })
    write_file(os.path.join(work_dir, "EncoderParam.txt"), content)


def make_yuv_frame(w, h, fill_y=128):
    """生成 packed YUV420p 帧（W*H + 2*(W/2)*(H/2) 字节）"""
    y = bytes([fill_y] * (w * h))
    u = bytes([128] * (w // 2 * h // 2))
    v = bytes([128] * (w // 2 * h // 2))
    return y + u + v


def wait_for(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.01)
    return False


def start_tool(work_dir):
    """启动 H264EncoderTools 子进程"""
    return subprocess.Popen(
        [TOOL, work_dir + "/"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def feed_frame(work_dir, index, w=DEFAULT_W, h=DEFAULT_H, frame_type=-1, yuv_data=None):
    """投递一帧 YUV + InFrameInfo"""
    if yuv_data is None:
        yuv_data = make_yuv_frame(w, h, fill_y=(index * 40 + 20) % 256)
    write_file(os.path.join(work_dir, f"YUV-{index}.yuv"), yuv_data, binary=True)
    ftype = 1 if index == 0 else frame_type
    info = json.dumps({
        "FrameType": ftype,
        "TimeStamp": index,
        "FrameSize": w * h * 3 // 2
    })
    write_file(os.path.join(work_dir, f"InFrameInfo-{index}.txt"), info)


def send_end(work_dir, early_exit=False):
    """写入结束信号"""
    content = json.dumps({"HasEnd": 1, "EarlyExit": 1 if early_exit else 0})
    write_file(os.path.join(work_dir, "InEnd.txt"), content)


def count_output_frames(work_dir):
    """统计输出帧数"""
    count = 0
    while os.path.exists(os.path.join(work_dir, f"H264-{count}.264")):
        count += 1
    return count


def read_out_end(work_dir):
    """读取 OutEnd.txt"""
    path = os.path.join(work_dir, "OutEnd.txt")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def verify_output_integrity(work_dir, expected_count):
    """验证输出帧的完整性：每帧有 .264 和 OutFrameInfo，且大小 > 0"""
    for i in range(expected_count):
        h264_path = os.path.join(work_dir, f"H264-{i}.264")
        info_path = os.path.join(work_dir, f"OutFrameInfo-{i}.txt")
        if not os.path.exists(h264_path):
            return False, f"H264-{i}.264 missing"
        if not os.path.exists(info_path):
            return False, f"OutFrameInfo-{i}.txt missing"
        if os.path.getsize(h264_path) == 0:
            return False, f"H264-{i}.264 is empty"
    return True, "ok"


# =============================================================================
# TEST CASES
# =============================================================================

def test_basic_5frames():
    """基础测试：5 帧正常编码"""
    work = make_work_dir("basic_5frames")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    for i in range(5):
        feed_frame(work, i)
        time.sleep(0.05)
        if proc.poll() is not None:
            return False, f"tool exited early at frame {i}"

    send_end(work)

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool did not exit after InEnd"

    out_end = read_out_end(work)
    if out_end is None:
        return False, "OutEnd.txt missing"
    if '"EarlyExit": 1' in out_end or '"Error": 1' in out_end:
        return False, f"unexpected OutEnd: {out_end}"

    count = count_output_frames(work)
    if count != 5:
        return False, f"expected 5 output frames, got {count}"

    ok, msg = verify_output_integrity(work, 5)
    if not ok:
        return False, msg
    return True, f"5 frames ok, exit code={proc.returncode}"


def test_rapid_100frames():
    """快速连续投递 100 帧后立即结束，验证输出帧数完整。
    
    这是关键回归测试：当前 EncodeAllFrames 先检查 InEnd 再检查帧，
    快速投递后立即写 InEnd 可能导致丢帧。
    """
    n = 100
    work = make_work_dir("rapid_100frames")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    # 无延迟连续投递全部帧
    for i in range(n):
        feed_frame(work, i)
        # 不等待，尽可能快速投递

    # 所有帧投递完毕后立即发送结束信号
    send_end(work)

    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool did not exit within 30s"

    out_end = read_out_end(work)
    if out_end is None:
        return False, "OutEnd.txt missing"
    if '"Error": 1' in out_end:
        return False, f"encoder error: {out_end}"

    count = count_output_frames(work)
    if count != n:
        return False, f"FRAME LOSS: expected {n} output frames, got {count} (lost {n - count})"

    ok, msg = verify_output_integrity(work, n)
    if not ok:
        return False, msg
    return True, f"{n} frames ok, no frame loss"


def test_truncated_yuv():
    """截断 YUV 文件（仅 Y 平面的一半），验证工具不崩溃。
    
    预期：工具应当报错退出或忽略该帧并在 OutEnd 中报告错误，
    而不是越界读取导致段错误。
    """
    work = make_work_dir("truncated_yuv")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    # 写一个正常帧
    feed_frame(work, 0)
    time.sleep(0.1)

    # 写一个截断帧（仅一半 Y 平面数据）
    truncated = bytes([128] * (DEFAULT_W * DEFAULT_H // 2))
    write_file(os.path.join(work, "YUV-1.yuv"), truncated, binary=True)
    info = json.dumps({"FrameType": -1, "TimeStamp": 1, "FrameSize": DEFAULT_W * DEFAULT_H * 3 // 2})
    write_file(os.path.join(work, "InFrameInfo-1.txt"), info)
    time.sleep(0.1)

    send_end(work)

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool hung after truncated YUV"

    # 工具应该正常退出（不是被信号杀死），无论是否输出帧
    if proc.returncode < 0:
        return False, f"tool crashed with signal {-proc.returncode}"

    return True, f"tool exited normally (code={proc.returncode}), no crash"


def test_empty_yuv():
    """空 YUV 文件，验证工具不越界"""
    work = make_work_dir("empty_yuv")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    # 写空帧
    write_file(os.path.join(work, "YUV-0.yuv"), b"", binary=True)
    info = json.dumps({"FrameType": 1, "TimeStamp": 0, "FrameSize": DEFAULT_W * DEFAULT_H * 3 // 2})
    write_file(os.path.join(work, "InFrameInfo-0.txt"), info)
    time.sleep(0.1)

    send_end(work)

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool hung on empty YUV"

    if proc.returncode < 0:
        return False, f"tool crashed with signal {-proc.returncode}"

    return True, f"tool handled empty YUV (code={proc.returncode})"


def test_wrong_framesize():
    """FrameSize 远大于实际 YUV 文件大小，验证不越界读取"""
    work = make_work_dir("wrong_framesize")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    # 正常大小 YUV 但 FrameSize 声明为 10x
    yuv = make_yuv_frame(DEFAULT_W, DEFAULT_H)
    write_file(os.path.join(work, "YUV-0.yuv"), yuv, binary=True)
    info = json.dumps({
        "FrameType": 1, "TimeStamp": 0,
        "FrameSize": DEFAULT_W * DEFAULT_H * 3 // 2 * 10  # 10x declared size
    })
    write_file(os.path.join(work, "InFrameInfo-0.txt"), info)
    time.sleep(0.1)

    send_end(work)

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool hung on wrong FrameSize"

    if proc.returncode < 0:
        return False, f"tool crashed with signal {-proc.returncode}"

    return True, f"tool handled mismatched FrameSize (code={proc.returncode})"


def test_concurrent():
    """两个编码实例使用不同工作目录并发运行，验证互不干扰"""
    n = 20
    results = [None, None]

    def run_instance(idx):
        work = make_work_dir(f"concurrent_{idx}")
        write_param(work)
        proc = start_tool(work)

        if not wait_for(os.path.join(work, "Header-0.dat"), timeout=15):
            results[idx] = (False, f"instance {idx}: Header timeout")
            return

        for i in range(n):
            feed_frame(work, i, fill_y=(idx * 100 + i) % 256)
            time.sleep(0.01)

        send_end(work)

        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            results[idx] = (False, f"instance {idx}: timeout")
            return

        count = count_output_frames(work)
        if count != n:
            results[idx] = (False, f"instance {idx}: expected {n} frames, got {count}")
            return

        results[idx] = (True, f"instance {idx}: {n} frames ok")

    def feed_frame(work, index, fill_y=128):
        """Local version with fill override"""
        yuv = make_yuv_frame(DEFAULT_W, DEFAULT_H, fill_y=fill_y)
        write_file(os.path.join(work, f"YUV-{index}.yuv"), yuv, binary=True)
        ftype = 1 if index == 0 else -1
        info = json.dumps({
            "FrameType": ftype, "TimeStamp": index,
            "FrameSize": DEFAULT_W * DEFAULT_H * 3 // 2
        })
        write_file(os.path.join(work, f"InFrameInfo-{index}.txt"), info)

    t0 = threading.Thread(target=run_instance, args=(0,))
    t1 = threading.Thread(target=run_instance, args=(1,))
    t0.start()
    t1.start()
    t0.join(timeout=60)
    t1.join(timeout=60)

    for i in range(2):
        if results[i] is None:
            return False, f"instance {i}: thread timeout"
        if not results[i][0]:
            return False, results[i][1]

    return True, f"both instances: {n} frames each, no interference"


def test_immediate_end():
    """无帧直接 InEnd，验证工具正常退出不挂起"""
    work = make_work_dir("immediate_end")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    # 不投递任何帧，直接结束
    send_end(work)

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool hung on immediate end (no frames)"

    out_end = read_out_end(work)
    if out_end is None:
        return False, "OutEnd.txt missing"

    count = count_output_frames(work)
    if count != 0:
        return False, f"expected 0 output frames, got {count}"

    return True, f"immediate end ok, exit code={proc.returncode}"


def test_early_exit():
    """投递几帧后发送 EarlyExit=1，验证工具快速退出"""
    work = make_work_dir("early_exit")
    write_param(work)
    proc = start_tool(work)

    if not wait_for(os.path.join(work, "Header-0.dat")):
        return False, "Header-0.dat timeout"

    for i in range(3):
        feed_frame(work, i)
        time.sleep(0.02)

    send_end(work, early_exit=True)

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool did not exit on EarlyExit"

    out_end = read_out_end(work)
    if out_end is None:
        return False, "OutEnd.txt missing"

    # EarlyExit 允许丢弃未编码帧，但不应崩溃
    if proc.returncode < 0:
        return False, f"tool crashed with signal {-proc.returncode}"

    return True, f"early exit ok, code={proc.returncode}"


def test_missing_param():
    """无 EncoderParam.txt，验证工具报错退出"""
    work = make_work_dir("missing_param")
    os.makedirs(work, exist_ok=True)
    # 不写 EncoderParam.txt

    proc = start_tool(work)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return False, "tool hung without EncoderParam.txt"

    if proc.returncode == 0:
        return False, "tool should have failed but returned 0"

    out_end = read_out_end(work)
    if out_end and '"Error": 1' in out_end:
        return True, f"correctly reported error, code={proc.returncode}"

    return True, f"failed as expected, code={proc.returncode}"


# 确定性用例的编码参数：与 GIF 生产场景一致。
# 886x1920 带 alpha 的内容会被 PAGEncoder 横向扩展为 886*2+4=1776 宽（alpha 放在右侧），
# 因此编码尺寸是 1776x1920，码率按原始内容尺寸 886x1920 计算。
DET_W, DET_H = 1776, 1920
DET_ORIG_W, DET_ORIG_H = 886, 1920
DET_FPS = 10.0
DET_FRAMES = 39
DET_RUNS = 5


def make_det_yuv_frame(w, h, index):
    """生成确定性的合成 YUV420p 帧。

    用固定噪声块按帧索引平移拼接：内容逐帧变化（模拟运动，让 VBV 与帧类型决策真正参与），
    但对同一 index 恒定可复现，因此可用于判定编码器自身是否确定。
    """
    block = bytes((i * 37 + i // 251 * 11) % 256 for i in range(65536))
    y_size = w * h
    uv_size = (w // 2) * (h // 2)
    total = y_size + uv_size * 2
    offset = (index * 4099) % len(block)
    reps = total // len(block) + 2
    buf = (block[offset:] + block * reps)[:total]
    return buf


def feed_det_frame(work_dir, index, yuv_data):
    write_file(os.path.join(work_dir, f"YUV-{index}.yuv"), yuv_data, binary=True)
    info = json.dumps({
        "FrameType": 1 if index == 0 else -1,
        "TimeStamp": index,
        "FrameSize": len(yuv_data),
    })
    write_file(os.path.join(work_dir, f"InFrameInfo-{index}.txt"), info)


def run_det_once(run_index, frames):
    """跑一次完整编码，返回全部输出码流拼接后的 sha256 与输出帧数。"""
    work = make_work_dir(f"determinism_{run_index}")
    content = json.dumps({
        "Width": DET_W, "Height": DET_H, "FrameRate": DET_FPS,
        "HasAlpha": 1, "MaxKeyFrameInterval": DEFAULT_MAX_KFI, "Quality": DEFAULT_QUALITY,
        "OriginalWidth": DET_ORIG_W, "OriginalHeight": DET_ORIG_H,
        # 可复现输出模式必须显式开启：缺省（0）时编码器使用帧级多线程，
        # 与 VBV 叠加会让输出字节依赖线程调度，本用例的断言只对开启态成立。
        "Deterministic": 1,
    })
    write_file(os.path.join(work, "EncoderParam.txt"), content)

    proc = start_tool(work)
    if not wait_for(os.path.join(work, "Header-1.dat"), timeout=30.0):
        proc.terminate()
        return None, 0, "headers not produced"

    for i, data in enumerate(frames):
        feed_det_frame(work, i, data)
    send_end(work)

    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.terminate()
        return None, 0, "tool hung"
    if proc.returncode != 0:
        return None, 0, f"tool exited with {proc.returncode}"

    digest = hashlib.sha256()
    # SPS/PPS 也纳入摘要：参数集变化同样会让产物字节不同。
    for header in ("Header-0.dat", "Header-1.dat"):
        with open(os.path.join(work, header), "rb") as f:
            digest.update(f.read())
    count = count_output_frames(work)
    for i in range(count):
        with open(os.path.join(work, f"H264-{i}.264"), "rb") as f:
            digest.update(f.read())
    return digest.hexdigest(), count, "ok"


def test_determinism():
    """开启 Deterministic 后，相同输入重复编码产出的码流字节必须完全一致。

    这是"产物可复现性"的编码器侧独立判据：本用例只驱动 H264EncoderTools，
    完全不经过解码与 RGBA 转换，因此失败即可断定问题在编码器侧。
    注意本用例显式开启了 Deterministic；默认（缺省）模式下多线程 + VBV 不保证字节一致，
    这是已知且刻意保留的行为。
    """
    frames = [make_det_yuv_frame(DET_W, DET_H, i) for i in range(DET_FRAMES)]
    digests = []
    for run in range(DET_RUNS):
        digest, count, msg = run_det_once(run, frames)
        if digest is None:
            return False, f"run {run} failed: {msg}"
        if count == 0:
            return False, f"run {run} produced no output frames"
        digests.append((digest, count))

    first = digests[0]
    for run, item in enumerate(digests[1:], start=1):
        if item != first:
            return False, (f"run {run} differs: {item[0][:16]}({item[1]} frames) "
                           f"vs run 0 {first[0][:16]}({first[1]} frames)")
    return True, f"{DET_RUNS} runs byte-identical, {first[1]} frames, sha256={first[0][:16]}"


# =============================================================================
# RUNNER
# =============================================================================

ALL_TESTS = [
    ("basic_5frames", test_basic_5frames),
    ("rapid_100frames", test_rapid_100frames),
    ("truncated_yuv", test_truncated_yuv),
    ("empty_yuv", test_empty_yuv),
    ("wrong_framesize", test_wrong_framesize),
    ("concurrent", test_concurrent),
    ("immediate_end", test_immediate_end),
    ("early_exit", test_early_exit),
    ("missing_param", test_missing_param),
    ("determinism", test_determinism),
]


def main():
    if not os.path.exists(TOOL):
        print(f"ERROR: tool not found at {TOOL}")
        print("  请先构建: cd H264EncoderTools && mkdir -p build && cd build && cmake .. && make")
        return 1

    print("=" * 70)
    print("H264EncoderTools 回归测试套件")
    print("=" * 70)

    passed = 0
    failed = 0
    failures = []

    # 允许通过命令行指定测试名
    filter_name = sys.argv[1] if len(sys.argv) > 1 else None

    for name, func in ALL_TESTS:
        if filter_name and filter_name not in name:
            continue
        print(f"\n[{name}] ", end="", flush=True)
        try:
            ok, msg = func()
        except Exception as e:
            ok, msg = False, f"exception: {e}"
        if ok:
            print(f"PASS - {msg}")
            passed += 1
        else:
            print(f"FAIL - {msg}")
            failed += 1
            failures.append((name, msg))

    print("\n" + "=" * 70)
    print(f"结果: {passed} passed, {failed} failed")
    if failures:
        print("\n失败列表:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
