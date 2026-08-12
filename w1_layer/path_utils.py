"""路径安全公共工具

统一三处重复的 _safe_path 实现（action.py / extended_tools.py / temp_manager.py）。
防目录遍历攻击：用 os.path.commonpath 防前缀碰撞（M1修复方案）。
"""
import os
from typing import Optional


def safe_resolve_path(path: str, sandbox_dir: str) -> Optional[str]:
    """安全路径检查：确保路径在 sandbox_dir 内

    Args:
        path: 用户输入的路径（绝对或相对）
        sandbox_dir: 沙箱根目录的绝对路径

    Returns:
        路径在沙箱内 → 返回绝对路径(str)
        路径越界 → 返回 None

    Examples:
        >>> safe_resolve_path("../../etc/passwd", "/data/sandbox")
        None
        >>> safe_resolve_path("file.txt", "/data/sandbox")
        '/data/sandbox/file.txt'
    """
    if not path:
        return None

    sandbox_abs = os.path.abspath(sandbox_dir)

    if os.path.isabs(path):
        full = os.path.abspath(path)
    else:
        full = os.path.abspath(os.path.join(sandbox_abs, path))

    # M1修复：用 commonpath 替代 startswith，防止前缀碰撞
    # （如 sandbox="/data/sandbox" 不会被 "/data/sandbox-secret" 误判）
    try:
        common = os.path.commonpath([full, sandbox_abs])
        if common != sandbox_abs:
            return None
    except ValueError:
        # 不同驱动器等情况
        return None

    return full


def safe_resolve_path_strict(path: str, sandbox_dir: str) -> str:
    """严格版安全路径检查：越界时抛 ValueError

    用于需要 fail-fast 的场景（如 action.py 的文件写入）。
    """
    result = safe_resolve_path(path, sandbox_dir)
    if result is None:
        raise ValueError(f"路径越界: {path}（限制在 {sandbox_dir}）")
    return result



def safe_join_path(user_path: str, allowed_root: str) -> Optional[str]:
    """安全路径拼接：将用户路径限制在 allowed_root 内

    用于 API 层校验用户传入的相对路径（如 save_dir、dir_path）。
    防止目录穿越攻击（如 "../../etc/passwd"）。

    Args:
        user_path: 用户输入的路径（通常为相对路径，也可能是绝对路径）
        allowed_root: 允许的根目录绝对路径

    Returns:
        路径在允许范围内 → 返回绝对路径(str)
        路径越界 → 返回 None

    Examples:
        >>> safe_join_path("images", "/proj/exports")
        '/proj/exports/images'
        >>> safe_join_path("../../etc/passwd", "/proj/exports")
        None
        >>> safe_join_path("/etc/passwd", "/proj/exports")
        None
    """
    if not user_path:
        return os.path.abspath(allowed_root)

    root_abs = os.path.abspath(allowed_root)

    # 用户路径拼接（若为绝对路径，os.path.join 会忽略 root_abs）
    full = os.path.abspath(os.path.join(root_abs, user_path))

    # 用 commonpath 防前缀碰撞（如 "/proj/exports" 不会被 "/proj/exports-evil" 误判）
    try:
        common = os.path.commonpath([full, root_abs])
        if common != root_abs:
            return None
    except ValueError:
        # 不同驱动器等情况
        return None

    return full
