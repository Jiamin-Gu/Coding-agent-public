"""内部规范化辅助函数。"""

import re

from .errors import ValidationError

_SKU_RE = re.compile(r"[A-Z0-9-]{1,20}")
_COUPON_RE = re.compile(r"[A-Z0-9]{3,16}")


def validate_sku(sku):
    """校验商品编码格式并返回它。"""
    if not isinstance(sku, str) or not _SKU_RE.fullmatch(sku):
        raise ValidationError("非法商品编码: {!r}".format(sku))
    return sku


def normalize_name(name):
    """去掉首尾空白，且不能为空。"""
    if not isinstance(name, str):
        raise ValidationError("名称必须是字符串: {!r}".format(name))
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("名称不能为空")
    return cleaned


def normalize_category(category):
    """去掉首尾空白并转成小写，且不能为空。"""
    if not isinstance(category, str):
        raise ValidationError("类别必须是字符串: {!r}".format(category))
    cleaned = category.strip().lower()
    if not cleaned:
        raise ValidationError("类别不能为空")
    return cleaned


def normalize_coupon_code(code):
    """去掉首尾空白并转成大写。"""
    if not isinstance(code, str):
        raise ValidationError("优惠券代码必须是字符串: {!r}".format(code))
    return code.strip().upper()


def validate_coupon_code(code):
    """规范化成大写并校验格式，返回规范化后的代码。"""
    normalized = normalize_coupon_code(code)
    if not _COUPON_RE.fullmatch(normalized):
        raise ValidationError("非法优惠券代码: {!r}".format(code))
    return normalized
