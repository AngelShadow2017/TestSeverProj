# charset_alias.py

CHARSET_ALIASES = {
    # ---- UTF 系列 ----
    'utf8': 'utf-8',
    'utf-8': 'utf-8',
    'utf_8': 'utf-8',
    'utf-8-sig': 'utf-8-sig',  # BOM 处理，直接保留

    # ---- ISO-8859 系列（西欧） ----
    'latin1': 'iso-8859-1',
    'latin-1': 'iso-8859-1',
    'iso_8859_1': 'iso-8859-1',
    'iso8859-1': 'iso-8859-1',
    'iso8859_1': 'iso-8859-1',
    'iso-8859-2': 'iso-8859-2',
    'latin2': 'iso-8859-2',
    'iso-8859-15': 'iso-8859-15',
    'latin9': 'iso-8859-15',

    # ---- GB 系列（简体中文） ----
    'gbk': 'gbk',
    'gb2312': 'gb2312',
    'gb18030': 'gb18030',
    'cp936': 'gbk',  # Windows 代码页映射

    # ---- Big5（繁体中文） ----
    'big5': 'big5',
    'big-5': 'big5',
    'big5hkscs': 'big5hkscs',

    # ---- Shift_JIS（日文） ----
    'shift_jis': 'shift_jis',
    'shift-jis': 'shift_jis',
    'sjis': 'shift_jis',
    'cp932': 'shift_jis',  # Windows 日文

    # ---- EUC-KR（韩文） ----
    'euc-kr': 'euc_kr',
    'euckr': 'euc_kr',
    'cp949': 'euc_kr',

    # ---- Windows 代码页 ----
    'cp1250': 'cp1250',
    'windows-1250': 'cp1250',
    'cp1251': 'cp1251',
    'windows-1251': 'cp1251',
    'cp1252': 'cp1252',
    'windows-1252': 'cp1252',
    'cp1256': 'cp1256',
    'windows-1256': 'cp1256',

    # ---- 其他常见 ----
    'koi8-r': 'koi8_r',
    'koi8-u': 'koi8_u',
    'macroman': 'mac_roman',
    'ascii': 'ascii',
    'us-ascii': 'ascii',

    # ---- 繁体/简体中文兼容别名 ----
    'chinese': 'gb2312',
    'csgb2312': 'gb2312',
    'csiso58gb231280': 'gb2312',
}


def normalize_charset(charset: str) -> str:
    """
    将 HTTP charset 字符串转换为 Python 可用的编码名称。
    若找不到映射，则返回原字符串（可能引发 LookupError）。
    """
    if not charset:
        return 'utf-8'  # 可根据需要修改默认值
    key = charset.lower().strip()
    return CHARSET_ALIASES.get(key, key)