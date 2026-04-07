#!/usr/bin/env python3
#这个是AI帮我生成的测试，用来测试recv切在奇奇怪怪的地方还能不能正常跑
import json
import os
import random
from pathlib import Path
from typing import List, Callable, Optional, Tuple

from httpResolver.fileResponser import HttpResponse, FileResponser
from server import default_mime_types

# 尝试导入用户实现的类（可根据实际路径修改）
try:
    from httpResolver.httpResolver import HttpStreamResolver, HttpRequestData, ErrorReason
except ImportError:
    # 如果无法导入，假设这些类已在全局作用域中定义
    try:
        HttpStreamResolver
        HttpRequestData
    except NameError:
        raise RuntimeError(
            "找不到 HttpStreamResolver 或 HttpRequestData。请先定义或正确导入它们。"
        )

# ========== 切分辅助函数 ==========
def random_slices_text(data: str, min_chunks: int = 1, max_chunks: int = 12) -> List[str]:
    """随机将字符串切成若干段"""
    if not data:
        return []
    length = len(data)
    chunks = random.randint(min_chunks, min(max_chunks, max(1, length)))
    if chunks <= 1:
        return [data]
    cut_points = sorted(random.sample(range(1, length), chunks - 1))
    parts = []
    last = 0
    for p in cut_points:
        parts.append(data[last:p])
        last = p
    parts.append(data[last:])
    return parts

def crlf_boundary_slices_text(data: str) -> List[str]:
    """在 CR 或 LF 边界处随机切分"""
    parts = []
    i = 0
    n = len(data)
    while i < n:
        j = i
        while j < n and data[j] not in ("\r", "\n"):
            j += 1
        if j >= n:
            parts.append(data[i:])
            break
        if random.random() < 0.5:
            parts.append(data[i:j])   # 切在 CR/LF 之前
            i = j
        else:
            parts.append(data[i:j+1]) # 包含 CR/LF
            i = j + 1
    return [p for p in parts if p]

def deterministic_split_at_text(data: str, indices: List[int]) -> List[str]:
    """在指定字符索引处切分"""
    parts = []
    last = 0
    for idx in indices:
        parts.append(data[last:idx])
        last = idx
    parts.append(data[last:])
    return [p for p in parts if p]

file_setting=FileResponser(Path(os.path.dirname(__file__),"httpRoot").resolve().__str__(),default_mime_types())

# ========== 手动测试入口 ==========
def manual_test(
    raw_request: str,
    callback: Optional[Callable[[bool, Optional[HttpRequestData]], None]] = None,
    trials: int = 5,
    seed: int = 123456,
    verbose: bool = True,
) -> List[List[Tuple[bool, Optional[HttpRequestData]]]]:
    """
    手动测试 HttpStreamResolver 的分段喂入能力。

    参数：
        raw_request : str 完整的 HTTP 请求字符串（包含 \r\n 等）
        callback    : 可选，自定义回调函数；若不提供则使用内部收集结果的回调
        trials      : 随机分段测试的次数
        seed        : 随机种子，保证可重现
        verbose     : 是否打印每次试验的细节

    返回：
        List[List[Tuple[bool, HttpRequestData|None]]]
        每个 trial 对应一个列表，列表内是本次试验中 resolver 产生的所有回调结果
    """
    random.seed(seed)

    all_trials_results = []

    for t in range(trials):
        # 收集回调结果
        collected = []
        def _cb(success: bool, data: Optional[HttpRequestData],error_reason: ErrorReason=ErrorReason.UNKNOWN):
            responser = HttpResponse(file_setting)
            responser.resolve(data)
            collected.append((success, data,responser.to_http_bytes().decode("utf-8"), error_reason))
            if callback:
                callback(success, data)

        resolver = HttpStreamResolver(_cb)

        # 随机选择切分策略
        r = random.random()
        if r < 0.25:
            parts = random_slices_text(raw_request, min_chunks=1, max_chunks=max(1, len(raw_request)//2))
            strategy = "random_slices"
        elif r < 0.6:
            parts = crlf_boundary_slices_text(raw_request)
            strategy = "crlf_boundary"
        else:
            if "User-Agent" in raw_request and random.random() < 0.7:
                idx = raw_request.find("User-Agent") + 5
                parts = deterministic_split_at_text(raw_request, [idx])
                strategy = "deterministic_useragent_cut"
            else:
                parts = random_slices_text(raw_request, min_chunks=2, max_chunks=8)
                strategy = "random_slices2"

        # 可选：对部分片段再次随机拆分，增加多样性
        if random.random() < 0.2:
            more = []
            for p in parts:
                if len(p) > 3 and random.random() < 0.5:
                    sub = random_slices_text(p, min_chunks=1, max_chunks=min(3, len(p)))
                    more.extend(sub)
                else:
                    more.append(p)
            parts = more

        # 依次喂入
        for chunk in parts:
            resolver.feed(chunk)

        if verbose:
            print(f"Trial {t+1}: strategy={strategy}, chunks={len(parts)}, sizes={[len(x) for x in parts]}")
            for i, (ok, d,resp, error_reason) in enumerate(collected):
                if ok and d is not None:
                    print(f"  callback[{i}]: OK \r\n{resp}")
                else:
                    print(f"  callback[{i}]: FAIL")
            print("-" * 40)

        all_trials_results.append(collected)

    return all_trials_results

# ========== 使用示例 ==========
if __name__ == "__main__":
    # 这里只是示例，实际使用时请注释掉或删除
    example_request = (
        "GET ../index.html HTTP/1.1\r\n"
        "Host: example.com\r\n"
        "User-Agent: test-client\r\n"
        "Accept: */*\r\n"
        "Content-Length: 3\r\n"
        "\r\n"
        "123"
        "GET /index.html HTTP/1.1\r\n"
        "Host: example2.com\r\n"
        "User-Agent: test-client2\r\n"
        "Accept: */*\r\n"
        "Content-Length: 5\r\n"
        "\r\n"
        "12345"
    )

    # 手动调用
    results = manual_test(example_request, trials=3000, verbose=True)